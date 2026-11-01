import csv
import io
import json

from manifest_py.manifest import Manifest, ManifestEntry
from manifest_py.serialize import dump_csv, dump_json, write_csv, write_json

HEADER = ["path", "size", "mtime", "sha256_or_error"]


def _manifest():
    return Manifest.from_entries(
        "/r",
        [
            ManifestEntry("/r/b", 2, 2.5, sha256="hb"),
            ManifestEntry("/r/a", None, None, error="ERROR: boom"),
        ],
    )


def test_dump_csv_rows():
    buf = io.StringIO()
    dump_csv(_manifest(), buf)
    rows = list(csv.reader(io.StringIO(buf.getvalue())))
    assert rows == [
        HEADER,
        ["/r/a", "", "", "ERROR: boom"],
        ["/r/b", "2", "2.5", "hb"],
    ]


def test_dump_csv_empty_manifest_has_only_header():
    buf = io.StringIO()
    dump_csv(Manifest("/r", ()), buf)
    assert list(csv.reader(io.StringIO(buf.getvalue()))) == [HEADER]


def test_dump_json_matches_to_dict():
    m = _manifest()
    buf = io.StringIO()
    dump_json(m, buf)
    assert json.loads(buf.getvalue()) == m.to_dict()


def test_dump_json_indent():
    m = _manifest()
    compact, pretty = io.StringIO(), io.StringIO()
    dump_json(m, compact, indent=None)
    dump_json(m, pretty)
    assert "\n" not in compact.getvalue()
    assert "\n" in pretty.getvalue()


def test_write_csv_file(tmp_path):
    out = tmp_path / "m.csv"
    write_csv(_manifest(), out)
    with open(out, newline="", encoding="utf-8") as f:
        assert next(csv.reader(f)) == HEADER


def test_write_json_file(tmp_path):
    m = _manifest()
    out = tmp_path / "m.json"
    write_json(m, out)
    assert json.loads(out.read_text(encoding="utf-8")) == m.to_dict()
