"""In-memory manifest data model."""

from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass
from typing import Any

__all__ = ["Manifest", "ManifestEntry"]


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
