import csv
import hashlib
import io
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from manifest_py.cli import app

runner: CliRunner = CliRunner()

HEADER: list[str] = ["path", "size", "mtime", "sha256_or_error"]


@pytest.fixture
def tree_a(tmp_path: Path) -> Path:
    d: Path = tmp_path / "a"
    (d / "sub").mkdir(parents=True)
    (d / "one.txt").write_text("hello")
    (d / "sub" / "two.txt").write_text("world!")
    return d


@pytest.fixture
def tree_b(tmp_path: Path) -> Path:
    d: Path = tmp_path / "b"
    d.mkdir()
    (d / "three.txt").write_text("xyz")
    return d


def paths(data: Mapping[str, Any]) -> list[str]:
    return [e["path"] for e in data["entries"]]


def test_default_is_json_to_stdout(tree_a: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a)])
    assert result.exit_code == 0
    data: dict[str, Any] = json.loads(result.stdout)
    assert data["root"] == str(tree_a)
    assert paths(data) == [str(tree_a / "one.txt"), str(tree_a / "sub" / "two.txt")]
    first: dict[str, Any] = data["entries"][0]
    assert first["size"] == 5
    assert first["sha256"] == hashlib.sha256(b"hello").hexdigest()
    assert first["error"] is None


def test_csv_to_stdout(tree_a: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a), "-f", "csv"])
    assert result.exit_code == 0
    rows: list[list[str]] = list(csv.reader(io.StringIO(result.stdout)))
    assert rows[0] == HEADER
    assert [r[0] for r in rows[1:]] == [
        str(tree_a / "one.txt"),
        str(tree_a / "sub" / "two.txt"),
    ]
    assert rows[1][3] == hashlib.sha256(b"hello").hexdigest()


def test_long_format_flag_json(tree_a: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a), "--format", "json"])
    assert result.exit_code == 0
    assert len(json.loads(result.stdout)["entries"]) == 2


def test_long_format_flag_csv(tree_a: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a), "--format", "csv"])
    assert result.exit_code == 0
    assert result.stdout.startswith(",".join(HEADER))


def test_invalid_format_rejected(tree_a: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a), "-f", "xml"])
    assert result.exit_code == 2


def test_multiple_roots_merged_and_sorted(tree_a: Path, tree_b: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_b), str(tree_a)])
    assert result.exit_code == 0
    data: dict[str, Any] = json.loads(result.stdout)
    assert paths(data) == sorted(paths(data))
    assert len(data["entries"]) == 3
    assert str(tree_b / "three.txt") in paths(data)
    assert str(tree_a / "one.txt") in paths(data)


def test_multiple_roots_csv(tree_a: Path, tree_b: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a), str(tree_b), "-f", "csv"])
    assert result.exit_code == 0
    rows: list[list[str]] = list(csv.reader(io.StringIO(result.stdout)))
    assert len(rows) == 4  # header + 3 files


def test_output_json_file(tree_a: Path, tmp_path: Path) -> None:
    out: Path = tmp_path / "out.json"
    result: Result = runner.invoke(app, [str(tree_a), "-o", str(out)])
    assert result.exit_code == 0
    assert result.stdout == ""
    assert len(json.loads(out.read_text())["entries"]) == 2


def test_output_csv_file(tree_a: Path, tmp_path: Path) -> None:
    out: Path = tmp_path / "out.csv"
    result: Result = runner.invoke(
        app, [str(tree_a), "--output", str(out), "-f", "csv"]
    )
    assert result.exit_code == 0
    assert result.stdout == ""
    with open(out, newline="") as f:
        rows: list[list[str]] = list(csv.reader(f))
    assert rows[0] == HEADER
    assert len(rows) == 3


def test_output_overwrites_existing_file(tree_a: Path, tmp_path: Path) -> None:
    out: Path = tmp_path / "out.json"
    out.write_text("stale")
    result: Result = runner.invoke(app, [str(tree_a), "-o", str(out)])
    assert result.exit_code == 0
    json.loads(out.read_text())


def test_unwritable_output_reports_error(tree_a: Path, tmp_path: Path) -> None:
    out: Path = tmp_path / "missing_dir" / "out.json"
    result: Result = runner.invoke(app, [str(tree_a), "-o", str(out)])
    assert result.exit_code == 1
    assert "cannot write output" in result.output


def test_empty_directory(tmp_path: Path) -> None:
    d: Path = tmp_path / "empty"
    d.mkdir()
    result: Result = runner.invoke(app, [str(d)])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["entries"] == []


def test_empty_directory_csv_has_only_header(tmp_path: Path) -> None:
    d: Path = tmp_path / "empty"
    d.mkdir()
    result: Result = runner.invoke(app, [str(d), "-f", "csv"])
    assert result.exit_code == 0
    assert list(csv.reader(io.StringIO(result.stdout))) == [HEADER]


def test_no_roots_is_usage_error() -> None:
    result: Result = runner.invoke(app, [])
    assert result.exit_code == 2


def test_nonexistent_root_is_usage_error(tmp_path: Path) -> None:
    result: Result = runner.invoke(app, [str(tmp_path / "nope")])
    assert result.exit_code == 2


def test_file_root_is_usage_error(tree_a: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a / "one.txt")])
    assert result.exit_code == 2


def test_one_bad_root_among_good_fails(tree_a: Path, tmp_path: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a), str(tmp_path / "nope")])
    assert result.exit_code == 2
    assert result.stdout == ""


def test_multiple_roots_root_is_common_ancestor(tree_a: Path, tree_b: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a), str(tree_b)])
    assert json.loads(result.stdout)["root"] == os.path.commonpath([tree_a, tree_b])


def test_overlapping_roots_deduplicate_files(tree_a: Path) -> None:
    result: Result = runner.invoke(app, [str(tree_a), str(tree_a)])
    assert len(json.loads(result.stdout)["entries"]) == 2
