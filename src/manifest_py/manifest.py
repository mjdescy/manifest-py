"""In-memory manifest data model."""

import hashlib
import os
from collections.abc import Callable, Iterable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any, NamedTuple

__all__ = ["Manifest", "ManifestDiff", "ManifestEntry", "ManifestMetadata"]

SCHEMA_VERSION = 1


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

    def content_hash(self) -> str:
        """Return a SHA-256 hex digest identifying the manifest's content.

        Covers each entry's path, size and SHA-256 (or error), in path order.
        mtime is excluded, matching what `diff` treats as a change. Fields
        are length-prefixed so different entry lists cannot collide.
        """
        h = hashlib.sha256()
        for e in self.entries:
            for field in (e.path, e.size, e.sha256, e.error):
                data: bytes = b"" if field is None else str(field).encode()
                h.update(len(data).to_bytes(8, "big"))
                h.update(data)
                h.update(b"\x00" if field is None else b"\x01")
        return h.hexdigest()

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dict of the manifest."""
        return {"entries": [asdict(e) for e in self.entries]}


@dataclass(frozen=True, slots=True)
class ManifestMetadata:
    """Facts about a manifest: when and how it was made, and its digest."""

    schema_version: int
    created: str
    tool_version: str
    roots: tuple[str, ...]
    entry_count: int
    total_size: int
    manifest_hash: str
    hash_algorithm: str = "sha256"

    @classmethod
    def for_manifest(
        cls, manifest: Manifest, roots: Iterable[str] = ()
    ) -> ManifestMetadata:
        """Describe `manifest`, computing its count, total size and hash."""
        try:
            tool_version: str = version("manifest-py")
        except PackageNotFoundError:
            tool_version = "unknown"
        return cls(
            schema_version=SCHEMA_VERSION,
            created=datetime.now(UTC).isoformat(timespec="seconds"),
            tool_version=tool_version,
            roots=tuple(roots),
            entry_count=len(manifest),
            total_size=sum(e.size or 0 for e in manifest),
            manifest_hash=manifest.content_hash(),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-compatible dict (`roots` becomes a list)."""
        d: dict[str, Any] = asdict(self)
        d["roots"] = list(self.roots)
        return d


class ManifestDiff(NamedTuple):
    """Result of `old.diff(new)`.

    `changed_before` and `changed_after` list the same files in the same
    order: the old and new version of each file that changed.
    """

    removed: Manifest
    added: Manifest
    changed_before: Manifest
    changed_after: Manifest
