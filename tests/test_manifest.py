import pytest

from manifest_py.manifest import Manifest, ManifestDiff, ManifestEntry


def _e(path: str, sha: str = "h", size: int = 1, mtime: float = 1.0) -> ManifestEntry:
    return ManifestEntry(path, size, mtime, sha256=sha)


def _m(*entries: ManifestEntry) -> Manifest:
    return Manifest.from_entries(entries)


def paths(m: Manifest) -> list[str]:
    return [e.path for e in m]


def test_from_entries_sorts_by_path() -> None:
    assert paths(_m(_e("b"), _e("a"), _e("c"))) == ["a", "b", "c"]


def test_iter_len_and_to_dict() -> None:
    m: Manifest = _m(_e("a"))
    assert len(m) == 1 and list(m) == [_e("a")]
    assert m.to_dict()["entries"][0]["path"] == "a"


# --- union ------------------------------------------------------------------


def test_union_combines_and_sorts() -> None:
    a: Manifest = _m(_e("r/c"), _e("r/a"))
    b: Manifest = _m(_e("r/b"))
    u: Manifest = Manifest.union(a, b)
    assert paths(u) == ["r/a", "r/b", "r/c"]
    assert len(a) == 2 and len(b) == 1


def test_union_single_manifest_returns_equal_manifest() -> None:
    m: Manifest = _m(_e("r/a"))
    assert Manifest.union(m) == m


def test_union_without_arguments_is_empty() -> None:
    assert len(Manifest.union()) == 0


def test_union_deduplicates_by_path_earliest_argument_wins() -> None:
    first: ManifestEntry = _e("x", "1")
    second: ManifestEntry = _e("x", "2")
    third: ManifestEntry = _e("x", "3")
    u: Manifest = Manifest.union(_m(first), _m(second, _e("y")), _m(third))
    assert paths(u) == ["x", "y"]
    assert u.entries[0] is first


def test_or_operator_is_union() -> None:
    a: Manifest = _m(_e("x", "mine"))
    b: Manifest = _m(_e("x", "theirs"), _e("y"))
    u: Manifest = a | b
    assert u == Manifest.union(a, b)
    assert u.entries[0].sha256 == "mine"


def test_or_with_non_manifest_is_not_supported() -> None:
    with pytest.raises(TypeError):
        _m() | 1  # type: ignore[operator]


# --- diff -------------------------------------------------------------------


def test_diff_of_identical_manifests_is_empty() -> None:
    m: Manifest = _m(_e("r/a"))
    d: ManifestDiff = m.diff(m)
    assert isinstance(d, ManifestDiff)
    assert all(len(part) == 0 for part in d)


def test_diff_classifies_removed_added_changed() -> None:
    old: Manifest = _m(_e("r/gone"), _e("r/same"), _e("r/mod", "1"))
    new: Manifest = _m(_e("r/same"), _e("r/mod", "2"), _e("r/fresh"))
    d: ManifestDiff = old.diff(new)
    assert paths(d.removed) == ["r/gone"]
    assert paths(d.added) == ["r/fresh"]
    assert [e.sha256 for e in d.changed_before] == ["1"]
    assert [e.sha256 for e in d.changed_after] == ["2"]


def test_diff_compares_absolute_paths() -> None:
    old: Manifest = _m(_e("/a/sub/f"))
    new: Manifest = _m(_e("/b/sub/f"))
    d: ManifestDiff = old.diff(new)
    assert paths(d.removed) == ["/a/sub/f"]
    assert paths(d.added) == ["/b/sub/f"]
    assert len(d.changed_before) == len(d.changed_after) == 0


def test_diff_ignores_mtime_but_detects_size_hash_and_error_changes() -> None:
    old: Manifest = _m(_e("r/t", mtime=1.0), _e("r/s", size=1), _e("r/e"))
    err: ManifestEntry = ManifestEntry("r/e", None, None, error="ERROR: x")
    new: Manifest = _m(_e("r/t", mtime=99.0), _e("r/s", size=2), err)
    assert paths(old.diff(new).changed_before) == ["r/e", "r/s"]


def test_diff_changed_sides_are_parallel_and_sorted() -> None:
    old: Manifest = _m(_e("o/b", "1"), _e("o/a", "1"))
    new: Manifest = _m(_e("n/a", "2"), _e("n/b", "2"))
    d: ManifestDiff = old.diff_relative_root(new, "o", "n")
    assert paths(d.changed_before) == ["o/a", "o/b"]
    assert paths(d.changed_after) == ["n/a", "n/b"]


def test_diff_is_directional() -> None:
    a: Manifest = _m(_e("r/x"))
    b: Manifest = _m(_e("r/y"))
    assert paths(a.diff(b).removed) == ["r/x"]
    assert paths(b.diff(a).added) == ["r/x"]


# --- diff_relative_root -----------------------------------------------------


def test_diff_relative_root_matches_across_roots() -> None:
    old: Manifest = _m(_e("/a/sub/f", "1"), _e("/a/gone"), _e("/a/same"))
    new: Manifest = _m(_e("/b/sub/f", "2"), _e("/b/fresh"), _e("/b/same"))
    d: ManifestDiff = old.diff_relative_root(new, "/a", "/b")
    assert paths(d.removed) == ["/a/gone"]
    assert paths(d.added) == ["/b/fresh"]
    assert paths(d.changed_before) == ["/a/sub/f"]
    assert paths(d.changed_after) == ["/b/sub/f"]


def test_diff_relative_root_roots_can_be_subdirectories() -> None:
    old: Manifest = _m(_e("/x/a/f"), _e("/x/a/g"))
    new: Manifest = _m(_e("/x/b/f", "2"), _e("/x/b/h"))
    d: ManifestDiff = old.diff_relative_root(new, "/x/a", "/x/b")
    assert paths(d.removed) == ["/x/a/g"]
    assert paths(d.added) == ["/x/b/h"]
    assert paths(d.changed_after) == ["/x/b/f"]


def test_content_hash_ignores_mtime_and_is_deterministic() -> None:
    a = Manifest.from_entries(
        [
            ManifestEntry("/r/b", 2, 1.0, sha256="hb"),
            ManifestEntry("/r/a", 1, 1.0, sha256="ha"),
        ]
    )
    b = Manifest.from_entries(
        [
            ManifestEntry("/r/a", 1, 9.0, sha256="ha"),
            ManifestEntry("/r/b", 2, 9.0, sha256="hb"),
        ]
    )
    assert a.content_hash() == b.content_hash()


def test_content_hash_detects_changes() -> None:
    a = Manifest.from_entries([ManifestEntry("/r/a", 1, 1.0, sha256="ha")])
    b = Manifest.from_entries([ManifestEntry("/r/a", 1, 1.0, sha256="hx")])
    c = Manifest.from_entries([ManifestEntry("/r/a", 1, 1.0, error="ha")])
    assert len({a.content_hash(), b.content_hash(), c.content_hash()}) == 3


def test_metadata_for_manifest() -> None:
    from manifest_py.manifest import ManifestMetadata

    m = Manifest.from_entries(
        [
            ManifestEntry("/r/a", 3, 1.0, sha256="ha"),
            ManifestEntry("/r/b", None, None, error="x"),
        ]
    )
    md = ManifestMetadata.for_manifest(m, ["/r"])
    assert (md.entry_count, md.total_size, md.roots) == (2, 3, ("/r",))
    assert md.manifest_hash == m.content_hash()
    assert md.to_dict()["roots"] == ["/r"]
