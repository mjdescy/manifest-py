"""In-memory manifest data model."""

import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass
from typing import Any, NamedTuple

__all__ = ["Manifest", "ManifestDiff", "ManifestEntry"]


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


def _content(entry: ManifestEntry) -> tuple[int | None, str | None, str | None]:
    """What makes two files "the same" when diffing (everything but mtime)."""
    return entry.size, entry.sha256, entry.error


@dataclass(frozen=True, slots=True)
class Manifest:
    """A collection of files, sorted by path.

    A manifest is just a list of files; they need not share a root directory.
    """

    entries: tuple[ManifestEntry, ...]

    @classmethod
    def from_entries(cls, entries: Iterable[ManifestEntry]) -> Manifest:
        """Build a manifest from entries in any order, sorting them by path."""
        return cls(tuple(sorted(entries, key=lambda e: e.path)))

    def diff(self, other: Manifest) -> ManifestDiff:
        """Compare this (old) manifest against `other` (new).

        Files are matched by their full `path`. A matched file counts as
        changed when its size, SHA-256 or error differs; mtime is ignored.
        To compare trees at different locations, use `diff_relative_root`.
        """
        return self._diff(other, lambda e: e.path, lambda e: e.path)

    def diff_relative_root(
        self, other: Manifest, self_root: str, other_root: str
    ) -> ManifestDiff:
        """Like `diff`, but match files by path relative to a root.

        `self_root` and `other_root` are the path prefixes excluded from the
        comparison for this manifest and for `other`.
        """
        return self._diff(
            other,
            lambda e: os.path.relpath(e.path, self_root),
            lambda e: os.path.relpath(e.path, other_root),
        )

    def _diff(
        self,
        other: Manifest,
        self_key: Callable[[ManifestEntry], str],
        other_key: Callable[[ManifestEntry], str],
    ) -> ManifestDiff:
        mine: dict[str, ManifestEntry] = {self_key(e): e for e in self.entries}
        theirs: dict[str, ManifestEntry] = {other_key(e): e for e in other.entries}
        changed: list[tuple[ManifestEntry, ManifestEntry]] = [
            (e, theirs[k])
            for k, e in mine.items()
            if k in theirs and _content(e) != _content(theirs[k])
        ]
        return ManifestDiff(
            removed=Manifest(tuple(e for k, e in mine.items() if k not in theirs)),
            added=Manifest(tuple(e for k, e in theirs.items() if k not in mine)),
            changed_before=Manifest(tuple(old for old, _ in changed)),
            changed_after=Manifest(tuple(new for _, new in changed)),
        )

    @classmethod
    def union(cls, *manifests: Manifest) -> Manifest:
        """Return one manifest with the entries of all `manifests`, sorted by path.

        Entries are deduplicated by path; when several manifests have the same
        path, the one from the earliest argument wins.
        """
        by_path: dict[str, ManifestEntry] = {}
        for m in reversed(manifests):
            by_path.update((e.path, e) for e in m.entries)
        return cls.from_entries(by_path.values())

    def __or__(self, other: Manifest) -> Manifest:
        if not isinstance(other, Manifest):
            return NotImplemented
        return Manifest.union(self, other)

    def __iter__(self) -> Iterator[ManifestEntry]:
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dict of the manifest."""
        return {"entries": [asdict(e) for e in self.entries]}


class ManifestDiff(NamedTuple):
    """Result of `old.diff(new)`.

    `changed_before` and `changed_after` list the same files in the same
    order: the old and new version of each file that changed.
    """

    removed: Manifest
    added: Manifest
    changed_before: Manifest
    changed_after: Manifest
