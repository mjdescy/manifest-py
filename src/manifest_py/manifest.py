"""In-memory manifest model with serializers for different output formats."""

import csv
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from os import PathLike
from typing import Any

__all__ = ["Manifest", "ManifestEntry"]

_CSV_HEADER = ["path", "size", "mtime", "sha256_or_error"]


@dataclass(frozen=True, slots=True)
class ManifestEntry:
    """One file in a manifest.

    Exactly one of `sha256` and `error` is set. `size` and `mtime` are None
    when the file's metadata could not be read.
    """

    path: str
    size: int | None
    mtime: float | None
    sha256: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class Manifest:
    """The files found under `root`, sorted by path."""

    root: str
    entries: tuple[ManifestEntry, ...]

    def __iter__(self) -> Iterator[ManifestEntry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dict of the manifest."""
        return {"root": self.root, "entries": [asdict(e) for e in self.entries]}

    def write_csv(self, out: str | PathLike[str]) -> None:
        """Write the manifest as CSV; the last column holds the digest or error."""
        with open(out, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(_CSV_HEADER)
            for e in self.entries:
                w.writerow([e.path, e.size, e.mtime, e.error or e.sha256])

    def write_json(self, out: str | PathLike[str], indent: int | None = 2) -> None:
        """Write the manifest as JSON."""
        with open(out, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=indent)
