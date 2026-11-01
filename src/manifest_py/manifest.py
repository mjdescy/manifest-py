"""In-memory manifest model with serializers for different output formats."""

import csv
import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from os import PathLike
from typing import Any

__all__ = ["Manifest", "ManifestBuilder", "ManifestEntry"]

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

    @classmethod
    def from_entries(cls, root: str, entries: Iterable[ManifestEntry]) -> Manifest:
        """Build a manifest from entries in any order, sorting them by path."""
        return cls(root, tuple(sorted(entries, key=lambda e: e.path)))

    def merge(self, other: Manifest) -> Manifest:
        """Return a new manifest with both manifests' entries, sorted by path.

        The result keeps this manifest's `root`. Entries are not deduplicated.
        """
        return Manifest.from_entries(self.root, (*self.entries, *other.entries))

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


class ManifestBuilder:
    """Mutable collector of entries that produces an immutable Manifest."""

    def __init__(self, root: str) -> None:
        self.root = root
        self._entries: list[ManifestEntry] = []

    def add(self, entry: ManifestEntry) -> None:
        """Add one entry."""
        self._entries.append(entry)

    def extend(self, entries: Iterable[ManifestEntry]) -> None:
        """Add several entries."""
        self._entries.extend(entries)

    def build(self) -> Manifest:
        """Return a snapshot of the entries added so far.

        Later additions to the builder do not affect manifests already built.
        """
        return Manifest.from_entries(self.root, self._entries)
