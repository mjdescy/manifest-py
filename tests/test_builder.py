import csv
import hashlib
import json
import os
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Self

import pytest

from manifest_py import builder
from manifest_py.builder import ManifestBuilder, _Entry, _scan, _sha256, _walk_parallel
from manifest_py.manifest import Manifest, ManifestEntry
from manifest_py.serialize import write_csv, write_json


def _build(root: str, workers: int = 32) -> Manifest:
    return ManifestBuilder.from_directory(root, workers)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "a.txt").write_text("hello")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("world!")
    (tmp_path / "sub" / "deep").mkdir()
    (tmp_path / "sub" / "deep" / "c.bin").write_bytes(b"\x00\x01\x02")
    (tmp_path / "empty").mkdir()
    return tmp_path


def test_scan_separates_files_and_dirs(tree: Path) -> None:
    files: list[_Entry]
    dirs: list[str]
    files, dirs = _scan(str(tree))
    assert [f[0] for f in files] == [str(tree / "a.txt")]
    assert sorted(dirs) == [str(tree / "empty"), str(tree / "sub")]
    entry: _Entry = files[0]
    assert entry.size == 5
    assert entry.mtime == os.stat(entry.path).st_mtime
    assert entry.error is None


def test_scan_does_not_follow_symlinks(tree: Path) -> None:
    (tree / "link_dir").symlink_to(tree / "sub", target_is_directory=True)
    (tree / "link_file").symlink_to(tree / "a.txt")
    files: list[_Entry]
    dirs: list[str]
    files, dirs = _scan(str(tree))
    assert [f[0] for f in files] == [str(tree / "a.txt")]
    assert str(tree / "link_dir") not in dirs


def test_scan_missing_path_returns_error_entry(tmp_path: Path) -> None:
    missing: str = str(tmp_path / "nope")
    files: list[_Entry]
    dirs: list[str]
    files, dirs = _scan(missing)
    assert dirs == []
    assert len(files) == 1
    entry: _Entry = files[0]
    assert isinstance(entry, _Entry)
    assert (entry.path, entry.size, entry.mtime) == (missing, None, None)
    assert entry.error is not None and entry.error.startswith("ERROR:")


def test_scan_stat_failure_only_affects_that_file(
    tree: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_scandir = os.scandir

    class FailingEntry:
        def __init__(self, e: os.DirEntry[str]) -> None:
            self.path: str = e.path
            self.name: str = e.name

        def is_dir(self, **kw: Any) -> bool:
            return False

        def is_file(self, **kw: Any) -> bool:
            return True

        def stat(self, **kw: Any) -> os.stat_result:
            raise PermissionError("denied")

    def fake_scandir(path: str) -> Any:
        real_it: Any = real_scandir(path)

        class Wrapper:
            def __enter__(self) -> Self:
                return self

            def __exit__(self, *a: object) -> None:
                real_it.close()

            def __iter__(self) -> Iterator[Any]:
                for e in real_it:
                    yield FailingEntry(e) if e.name == "bad.txt" else e

        return Wrapper()

    (tree / "bad.txt").write_text("x")
    monkeypatch.setattr(os, "scandir", fake_scandir)
    files: list[_Entry]
    dirs: list[str]
    files, dirs = _scan(str(tree))
    by_path: dict[str, _Entry] = {f.path: f for f in files}
    bad_error: str | None = by_path[str(tree / "bad.txt")].error
    assert bad_error is not None and bad_error.startswith("ERROR:")
    assert by_path[str(tree / "a.txt")].error is None
    assert str(tree / "sub") in dirs


def test_walk_parallel_finds_all_files(tree: Path) -> None:
    with ThreadPoolExecutor(4) as pool:
        found: set[str] = {f[0] for f in _walk_parallel(str(tree), pool)}
    assert found == {
        str(tree / "a.txt"),
        str(tree / "sub" / "b.txt"),
        str(tree / "sub" / "deep" / "c.bin"),
    }


def test_walk_parallel_empty_dir(tmp_path: Path) -> None:
    with ThreadPoolExecutor(2) as pool:
        assert list(_walk_parallel(str(tmp_path), pool)) == []


def test_sha256_matches_hashlib(tmp_path: Path) -> None:
    p: Path = tmp_path / "f"
    p.write_bytes(b"abc")
    assert _sha256(str(p)) == hashlib.sha256(b"abc").hexdigest()


def test_sha256_empty_file(tmp_path: Path) -> None:
    p: Path = tmp_path / "f"
    p.write_bytes(b"")
    assert _sha256(str(p)) == hashlib.sha256(b"").hexdigest()


def test_sha256_missing_file_returns_error(tmp_path: Path) -> None:
    assert _sha256(str(tmp_path / "nope")).startswith("ERROR:")


def test_failed_scan_is_not_hashed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def fake_sha256(p: str) -> str:
        calls.append(p)
        return "h"

    monkeypatch.setattr(builder, "_sha256", fake_sha256)
    _build(str(tmp_path / "nope"), workers=2)
    assert calls == []


def _read(out: Path) -> list[list[str]]:
    with open(out, newline="", encoding="utf-8") as f:
        return list(csv.reader(f))


def test_from_directory_contents(tree: Path, tmp_path: Path) -> None:
    out: Path = tmp_path / "out.csv"
    write_csv(_build(str(tree), workers=4), out)
    rows: list[list[str]] = _read(out)

    assert rows[0] == ["path", "size", "mtime", "sha256_or_error"]
    body: list[list[str]] = rows[1:]
    paths: list[str] = [r[0] for r in body]
    assert paths == sorted(paths)
    assert paths == [
        str(tree / "a.txt"),
        str(tree / "sub" / "b.txt"),
        str(tree / "sub" / "deep" / "c.bin"),
    ]
    by_path: dict[str, list[str]] = {r[0]: r for r in body}
    a: list[str] = by_path[str(tree / "a.txt")]
    assert a[1] == "5"
    assert a[3] == hashlib.sha256(b"hello").hexdigest()


def test_from_directory_missing_root_writes_error_row(tmp_path: Path) -> None:
    out: Path = tmp_path / "out.csv"
    missing: str = str(tmp_path / "nope")
    write_csv(_build(missing, workers=2), out)
    rows: list[list[str]] = _read(out)
    assert len(rows) == 2
    assert rows[1][0] == missing
    assert rows[1][1] == rows[1][2] == ""
    assert rows[1][3].startswith("ERROR:")


def test_from_directory_unreadable_file_reports_error(
    tree: Path, tmp_path: Path
) -> None:
    if os.geteuid() == 0:
        pytest.skip("root can read anything")
    secret: Path = tree / "secret.txt"
    secret.write_text("x")
    secret.chmod(0)
    out: Path = tmp_path / "out.csv"
    try:
        write_csv(_build(str(tree), workers=2), out)
    finally:
        secret.chmod(0o600)
    row: list[str] = next(r for r in _read(out) if r[0] == str(secret))
    assert row[3].startswith("ERROR:")


def test_public_api_is_only_manifest_builder() -> None:
    assert builder.__all__ == ["ManifestBuilder"]


def test_from_directory_returns_manifest(tree: Path) -> None:
    m: Manifest = _build(str(tree), workers=2)
    assert m.root == str(tree)
    assert [e.path for e in m] == sorted(e.path for e in m)
    a: ManifestEntry = next(e for e in m if e.path == str(tree / "a.txt"))
    assert a.size == 5
    assert a.sha256 == hashlib.sha256(b"hello").hexdigest()
    assert a.error is None


def test_from_directory_missing_root_sets_error(tmp_path: Path) -> None:
    e: ManifestEntry
    (e,) = _build(str(tmp_path / "nope"), workers=2)
    assert e.sha256 is None
    assert e.size is None and e.mtime is None
    assert e.error is not None and e.error.startswith("ERROR:")


def test_write_json_round_trips(tree: Path, tmp_path: Path) -> None:
    m: Manifest = _build(str(tree), workers=2)
    out: Path = tmp_path / "out.json"
    write_json(m, out)
    assert json.loads(out.read_text(encoding="utf-8")) == m.to_dict()


def _e(path: str) -> ManifestEntry:
    return ManifestEntry(path, 1, 1.0, sha256="h")


def test_builder_builds_sorted_snapshot() -> None:
    b: ManifestBuilder = ManifestBuilder("r")
    b.add(_e("b"))
    b.extend([_e("c"), _e("a")])
    first: Manifest = b.build()
    b.add(_e("d"))
    assert [e.path for e in first] == ["a", "b", "c"]
    assert [e.path for e in b.build()] == ["a", "b", "c", "d"]
    assert b.build().root == "r"


def test_from_directory_returns_sorted_manifest(tree: Path) -> None:
    m: Manifest = ManifestBuilder.from_directory(str(tree), workers=2)
    assert isinstance(m, Manifest)
    assert m.root == str(tree)
    paths: list[str] = [e.path for e in m]
    assert paths == sorted(paths) and len(paths) == 3
