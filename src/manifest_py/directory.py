"""Build a manifest (path, size, mtime, SHA-256) of a directory tree."""

import hashlib
import os
from collections.abc import Iterator
from concurrent.futures import FIRST_COMPLETED, Executor, ThreadPoolExecutor, wait
from typing import NamedTuple

from manifest_py.manifest import Manifest, ManifestEntry

__all__ = ["build_manifest"]

_ERROR_PREFIX = "ERROR: "


class _Entry(NamedTuple):
    """One file found by a scan. `error` is set if it could not be read."""

    path: str
    size: int | None
    mtime: float | None
    error: str | None = None


# --- Scanning ---------------------------------------------------------------


def _scan(path: str) -> tuple[list[_Entry], list[str]]:
    """List one directory (non-recursive): its files and its subdirectory paths.

    Symlinks are not followed. Failures become error entries instead of raising.
    """
    files: list[_Entry] = []
    dirs: list[str] = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    if e.is_dir(follow_symlinks=False):
                        dirs.append(e.path)
                    elif e.is_file(follow_symlinks=False):
                        st = e.stat(follow_symlinks=False)
                        files.append(_Entry(e.path, st.st_size, st.st_mtime))
                except OSError as err:
                    files.append(_Entry(e.path, None, None, f"ERROR: {err}"))
    except OSError as err:
        # Entries gathered before the failure are kept alongside the error.
        files.append(_Entry(path, None, None, f"ERROR: {err}"))
    return files, dirs


def _walk_parallel(root: str, pool: Executor) -> Iterator[_Entry]:
    """Yield every file under `root`, scanning directories concurrently.

    Order is not deterministic.
    """
    pending = {pool.submit(_scan, root)}
    while pending:
        done, pending = wait(pending, return_when=FIRST_COMPLETED)
        for fut in done:
            files, dirs = fut.result()
            yield from files
            pending |= {pool.submit(_scan, d) for d in dirs}


# --- Hashing ----------------------------------------------------------------


def _sha256(path: str) -> str:
    """Return the file's SHA-256 hex digest, or an `ERROR: ...` string."""
    try:
        with open(path, "rb") as f:
            return hashlib.file_digest(f, "sha256").hexdigest()
    except OSError as err:
        return f"ERROR: {err}"


def _digest(entry: _Entry) -> str:
    """Return the entry's existing scan error, or else its SHA-256 digest."""
    return entry.error or _sha256(entry.path)


# --- Public API -------------------------------------------------------------


def build_manifest(root: str, workers: int = 32) -> Manifest:
    """Return a Manifest of every file under `root`, sorted by path.

    Each entry has the file's size (bytes), mtime (epoch seconds) and SHA-256.
    Anything that could not be read (a directory, a file's metadata, or a
    file's contents) is reported in the entry's `error` field rather than
    raising. Serialize the result with `Manifest.write_csv` or `write_json`.

    `workers` is the number of threads used for scanning and hashing.
    """
    with ThreadPoolExecutor(workers) as pool:
        entries = sorted(_walk_parallel(root, pool))
        digests = pool.map(_digest, entries)
        return Manifest.from_entries(
            root,
            (
                ManifestEntry(e.path, e.size, e.mtime, error=d)
                if d.startswith(_ERROR_PREFIX)
                else ManifestEntry(e.path, e.size, e.mtime, sha256=d)
                for e, d in zip(entries, digests)
            ),
        )
