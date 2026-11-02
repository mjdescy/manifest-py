import csv
import io
import json
from pathlib import Path

from manifest_py.manifest import Manifest, ManifestEntry
from manifest_py.serialize import dump_csv, dump_json, write_csv, write_json

HEADER: list[str] = ["path", "size", "mtime", "sha256_or_error"]


def _manifest() -> Manifest:
    return Manifest.from_entries(
        [
            ManifestEntry("/r/b", 2, 2.5, sha256="hb"),
            ManifestEntry("/r/a", None, None, error="ERROR: boom"),
        ],
    )


def test_dump_csv_rows() -> None:
    buf: io.StringIO = io.StringIO()
    dump_csv(_manifest(), buf)
    rows: list[list[str]] = list(csv.reader(io.StringIO(buf.getvalue())))
    assert rows == [
        HEADER,
        ["/r/a", "", "", "ERROR: boom"],
        ["/r/b", "2", "2.5", "hb"],
    ]


def test_dump_csv_empty_manifest_has_only_header() -> None:
    buf: io.StringIO = io.StringIO()
    dump_csv(Manifest(()), buf)
    assert list(csv.reader(io.StringIO(buf.getvalue()))) == [HEADER]


def test_dump_json_matches_to_dict() -> None:
    m: Manifest = _manifest()
    buf: io.StringIO = io.StringIO()
    dump_json(m, buf)
    assert json.loads(buf.getvalue()) == m.to_dict()


def test_dump_json_indent() -> None:
    m: Manifest = _manifest()
    compact: io.StringIO = io.StringIO()
    pretty: io.StringIO = io.StringIO()
    dump_json(m, compact, indent=None)
    dump_json(m, pretty)
    assert "\n" not in compact.getvalue()
    assert "\n" in pretty.getvalue()


def test_write_csv_file(tmp_path: Path) -> None:
    out: Path = tmp_path / "m.csv"
    write_csv(_manifest(), out)
    with open(out, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == HEADER


def test_write_json_file(tmp_path: Path) -> None:
    m: Manifest = _manifest()
    out: Path = tmp_path / "m.json"
    write_json(m, out)
    assert json.loads(out.read_text(encoding="utf-8")) == m.to_dict()
