"""In-memory manifest data model."""

import os
from collections.abc import Iterable, Iterator
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


def _relpath(entry: ManifestEntry, root: str) -> str:
    return os.path.relpath(entry.path, root)


def _content(entry: ManifestEntry) -> tuple[int | None, str | None, str | None]:
    """What makes two files "the same" when diffing (everything but mtime)."""
    return entry.size, entry.sha256, entry.error


@dataclass(frozen=True, slots=True)
class Manifest:
    """The files found under `root`, sorted by path."""

    root: str
    entries: tuple[ManifestEntry, ...]

    @classmethod
    def from_entries(cls, root: str, entries: Iterable[ManifestEntry]) -> Manifest:
        """Build a manifest from entries in any order, sorting them by path."""
        return cls(root, tuple(sorted(entries, key=lambda e: e.path)))

    def diff(self, other: Manifest) -> ManifestDiff:
        """Compare this (old) manifest against `other` (new).

        Files are matched by path relative to each manifest's `root`, so two
        trees at different locations can be compared. A matched file counts as
        changed when its size, SHA-256 or error differs; mtime is ignored.
        """
        mine = {_relpath(e, self.root): e for e in self.entries}
        theirs = {_relpath(e, other.root): e for e in other.entries}
        changed = [
            (e, theirs[k])
            for k, e in mine.items()
            if k in theirs and _content(e) != _content(theirs[k])
        ]
        return ManifestDiff(
            removed=Manifest(
                self.root, tuple(e for k, e in mine.items() if k not in theirs)
            ),
            added=Manifest(
                other.root, tuple(e for k, e in theirs.items() if k not in mine)
            ),
            changed_before=Manifest(self.root, tuple(old for old, _ in changed)),
            changed_after=Manifest(other.root, tuple(new for _, new in changed)),
        )

    @classmethod
    def union(cls, *manifests: Manifest, root: str | None = None) -> Manifest:
        """Return one manifest with the entries of all `manifests`, sorted by path.

        Entries are deduplicated by path; when several manifests have the same
        path, the one from the earliest argument wins.

        `root` defaults to the shared root if all manifests have the same one,
        otherwise their closest common ancestor directory. At least one
        manifest, or an explicit `root`, is required.
        """
        if root is None:
            if not manifests:
                raise ValueError("union() needs at least one manifest or a root")
            roots = {m.root for m in manifests}
            root = (
                roots.pop()
                if len(roots) == 1
                else os.path.commonpath([os.path.abspath(r) for r in roots])
            )
        by_path: dict[str, ManifestEntry] = {}
        for m in reversed(manifests):
            by_path.update((e.path, e) for e in m.entries)
        return cls.from_entries(root, by_path.values())

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
        return {"root": self.root, "entries": [asdict(e) for e in self.entries]}


class ManifestDiff(NamedTuple):
    """Result of `old.diff(new)`.

    `changed_before` and `changed_after` list the same files in the same
    order: the old and new version of each file that changed.
    """

    removed: Manifest
    added: Manifest
    changed_before: Manifest
    changed_after: Manifest
