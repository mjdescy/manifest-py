"""Serialize a Manifest to CSV or JSON, to a text stream or a file."""

import csv
import json
from os import PathLike
from typing import TextIO

from manifest_py.manifest import Manifest

__all__ = ["dump_csv", "dump_json", "write_csv", "write_json"]

_CSV_HEADER = ["path", "size", "mtime", "sha256_or_error"]


def dump_csv(manifest: Manifest, fp: TextIO) -> None:
    """Write the manifest as CSV to a text stream (opened with newline="")."""
    w = csv.writer(fp)
    w.writerow(_CSV_HEADER)
    for e in manifest:
        w.writerow([e.path, e.size, e.mtime, e.error or e.sha256])


def dump_json(manifest: Manifest, fp: TextIO, indent: int | None = 2) -> None:
    """Write the manifest as JSON to a text stream."""
    json.dump(manifest.to_dict(), fp, indent=indent)


def write_csv(manifest: Manifest, out: str | PathLike[str]) -> None:
    """Write the manifest as CSV; the last column holds the digest or error."""
    with open(out, "w", newline="", encoding="utf-8") as f:
        dump_csv(manifest, f)


def write_json(
    manifest: Manifest, out: str | PathLike[str], indent: int | None = 2
) -> None:
    """Write the manifest as JSON."""
    with open(out, "w", encoding="utf-8") as f:
        dump_json(manifest, f, indent)
