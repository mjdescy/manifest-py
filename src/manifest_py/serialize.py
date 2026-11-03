"""Serialize a Manifest to CSV or JSON, to a text stream or a file."""

import csv
import json
from _csv import Writer
from os import PathLike
from pathlib import Path
from typing import Any, TextIO

from manifest_py.manifest import Manifest, ManifestMetadata

__all__ = [
    "dump_csv",
    "dump_json",
    "dump_metadata_csv",
    "metadata_sidecar_path",
    "write_csv",
    "write_json",
    "write_metadata_csv",
]

_CSV_HEADER = ["path", "size", "mtime", "sha256_or_error"]


def dump_csv(manifest: Manifest, fp: TextIO) -> None:
    """Write the manifest as CSV to a text stream (opened with newline="")."""
    w: Writer = csv.writer(fp)
    w.writerow(_CSV_HEADER)
    for e in manifest:
        w.writerow([e.path, e.size, e.mtime, e.error or e.sha256])


def dump_json(
    manifest: Manifest,
    fp: TextIO,
    indent: int | None = 2,
    metadata: ManifestMetadata | None = None,
) -> None:
    """Write the manifest as JSON to a text stream.

    With `metadata`, a "metadata" key precedes "entries".
    """
    data: dict[str, Any] = manifest.to_dict()
    if metadata is not None:
        data = {"metadata": metadata.to_dict(), **data}
    json.dump(data, fp, indent=indent)


def dump_metadata_csv(metadata: ManifestMetadata, fp: TextIO) -> None:
    """Write metadata as a one-row CSV table (header plus one data row).

    `roots` is joined into one cell with ";".
    """
    d: dict[str, Any] = metadata.to_dict()
    d["roots"] = ";".join(metadata.roots)
    w: Writer = csv.writer(fp)
    w.writerow(d.keys())
    w.writerow(d.values())


def metadata_sidecar_path(out: str | PathLike[str]) -> Path:
    """Return the sidecar path for a manifest file: `m.csv` -> `m.meta.csv`."""
    return Path(out).with_suffix(".meta.csv")


def write_metadata_csv(metadata: ManifestMetadata, out: str | PathLike[str]) -> None:
    """Write metadata as a one-row CSV file."""
    with open(out, "w", newline="", encoding="utf-8") as f:
        dump_metadata_csv(metadata, f)


def write_csv(manifest: Manifest, out: str | PathLike[str]) -> None:
    """Write the manifest as CSV; the last column holds the digest or error."""
    with open(out, "w", newline="", encoding="utf-8") as f:
        dump_csv(manifest, f)


def write_json(
    manifest: Manifest,
    out: str | PathLike[str],
    indent: int | None = 2,
    metadata: ManifestMetadata | None = None,
) -> None:
    """Write the manifest as JSON."""
    with open(out, "w", encoding="utf-8") as f:
        dump_json(manifest, f, indent, metadata)
