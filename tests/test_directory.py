import csv
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor

import pytest

from manifest_py import directory
from manifest_py.directory import _Entry, _scan, _sha256, _walk_parallel, build_manifest


@pytest.fixture
def tree(tmp_path):
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world!")
    (tmp_path / "sub" / "deep").mkdir()
    (tmp_path / "sub" / "deep" / "c.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / "empty").mkdir()
    return tmp_path


def test_scan_separates_files_and_dirs(tree):
    files, dirs = _scan(str(tree))
    assert [f[0] for f in files] == [str(tree / "a.txt")]
    assert sorted(dirs) == [str(tree / "empty"), str(tree / "sub")]
    entry = files[0]
    assert entry.size == 5
    assert entry.mtime == os.stat(entry.path).st_mtime
    assert entry.error is None


def test_scan_does_not_follow_symlinks(tree):
    (tree / "link_dir").symlink_to(tree / "sub", target_is_directory=True)
    (tree / "link_file").symlink_to(tree / "a.txt")
    files, dirs = _scan(str(tree))
    assert [f[0] for f in files] == [str(tree / "a.txt")]
    assert str(tree / "link_dir") not in dirs


def test_scan_missing_path_returns_error_entry(tmp_path):
    missing = str(tmp_path / "nope")
    files, dirs = _scan(missing)
    assert dirs == []
    assert len(files) == 1
    entry = files[0]
    assert isinstance(entry, _Entry)
    assert (entry.path, entry.size, entry.mtime) == (missing, None, None)
    assert entry.error.startswith("ERROR:")


def test_scan_stat_failure_only_affects_that_file(tree, monkeypatch):
    real_scandir = os.scandir

    def fake_scandir(path):
        real_it = real_scandir(path)

        class Wrapper:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                real_it.close()

            def __iter__(self):
                for e in real_it:
                    yield FailingEntry(e) if e.name == "bad.txt" else e

        return Wrapper()

    class FailingEntry:
        def __init__(self, e):
            self.path = e.path
            self.name = e.name

        def is_dir(self, **kw):
            return False

        def is_file(self, **kw):
            return True

        def stat(self, **kw):
            raise PermissionError("denied")

    (tree / "bad.txt").write_text("x")
    monkeypatch.setattr(directory.os, "scandir", fake_scandir)
    files, dirs = _scan(str(tree))
    by_path = {f.path: f for f in files}
    assert by_path[str(tree / "bad.txt")].error.startswith("ERROR:")
    assert by_path[str(tree / "a.txt")].error is None
    assert str(tree / "sub") in dirs


def test_walk_parallel_finds_all_files(tree):
    with ThreadPoolExecutor(4) as pool:
        found = {f[0] for f in _walk_parallel(str(tree), pool)}
    assert found == {
        str(tree / "a.txt"),
        str(tree / "sub" / "b.txt"),
        str(tree / "sub" / "deep" / "c.bin"),
    }


def test_walk_parallel_empty_dir(tmp_path):
    with ThreadPoolExecutor(2) as pool:
        assert list(_walk_parallel(str(tmp_path), pool)) == []


def test_sha256_matches_hashlib(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"abc")
    assert _sha256(str(p)) == hashlib.sha256(b"abc").hexdigest()


def test_sha256_empty_file(tmp_path):
    p = tmp_path / "f"
    p.write_bytes(b"")
    assert _sha256(str(p)) == hashlib.sha256(b"").hexdigest()


def test_sha256_missing_file_returns_error(tmp_path):
    assert _sha256(str(tmp_path / "nope")).startswith("ERROR:")


def test_failed_scan_is_not_hashed(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(directory, "_sha256", lambda p: calls.append(p) or "h")
    build_manifest(str(tmp_path / "nope"), workers=2)
    assert calls == []


def _read(out):
    with open(out, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_build_manifest_contents(tree, tmp_path):
    out = tmp_path / "out.csv"
    build_manifest(str(tree), workers=4).write_csv(out)
    rows = _read(out)

    assert rows[0] == ["path", "size", "mtime", "sha256_or_error"]
    body = rows[1:]
    paths = [r[0] for r in body]
    assert paths == sorted(paths)
    assert paths == [
        str(tree / "a.txt"),
        str(tree / "sub" / "b.txt"),
        str(tree / "sub" / "deep" / "c.bin"),
    ]
    by_path = {r[0]: r for r in body}
    a = by_path[str(tree / "a.txt")]
    assert a[1] == "5"
    assert a[3] == hashlib.sha256(b"hello").hexdigest()


def test_build_manifest_missing_root_writes_error_row(tmp_path):
    out = tmp_path / "out.csv"
    missing = str(tmp_path / "nope")
    build_manifest(missing, workers=2).write_csv(out)
    rows = _read(out)
    assert len(rows) == 2
    assert rows[1][0] == missing
    assert rows[1][1] == rows[1][2] == ""
    assert rows[1][3].startswith("ERROR:")


def test_build_manifest_unreadable_file_reports_error(tree, tmp_path):
    if os.geteuid() == 0:
        pytest.skip("root can read anything")
    secret = tree / "secret.txt"
    secret.write_text("x")
    secret.chmod(0)
    out = tmp_path / "out.csv"
    try:
        build_manifest(str(tree), workers=2).write_csv(out)
    finally:
        secret.chmod(0o600)
    row = next(r for r in _read(out) if r[0] == str(secret))
    assert row[3].startswith("ERROR:")


def test_public_api_is_only_build_manifest():
    assert directory.__all__ == ["build_manifest"]


def test_build_manifest_returns_manifest(tree):
    m = build_manifest(str(tree), workers=2)
    assert m.root == str(tree)
    assert [e.path for e in m] == sorted(e.path for e in m)
    a = next(e for e in m if e.path == str(tree / "a.txt"))
    assert a.size == 5
    assert a.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert a.error is None


def test_build_manifest_missing_root_sets_error(tmp_path):
    (e,) = build_manifest(str(tmp_path / "nope"), workers=2)
    assert e.sha256 is None
    assert e.size is None and e.mtime is None
    assert e.error.startswith("ERROR:")


def test_write_json_round_trips(tree, tmp_path):
    m = build_manifest(str(tree), workers=2)
    out = tmp_path / "out.json"
    m.write_json(out)
    assert json.loads(out.read_text(encoding="utf-8")) == m.to_dict()
