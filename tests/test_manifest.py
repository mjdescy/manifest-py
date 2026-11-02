import os

import pytest

from manifest_py.manifest import Manifest, ManifestDiff, ManifestEntry


def _e(path: str, sha: str = "h", size: int = 1, mtime: float = 1.0) -> ManifestEntry:
    return ManifestEntry(path, size, mtime, sha256=sha)


def _m(root: str, *entries: ManifestEntry) -> Manifest:
    return Manifest.from_entries(root, entries)


def paths(m: Manifest) -> list[str]:
    return [e.path for e in m]


def test_from_entries_sorts_by_path() -> None:
    assert paths(_m("r", _e("b"), _e("a"), _e("c"))) == ["a", "b", "c"]


def test_iter_len_and_to_dict() -> None:
    m: Manifest = _m("r", _e("a"))
    assert len(m) == 1 and list(m) == [_e("a")]
    assert m.to_dict()["root"] == "r"
    assert m.to_dict()["entries"][0]["path"] == "a"


# --- union ------------------------------------------------------------------


def test_union_combines_and_sorts() -> None:
    a: Manifest = _m("r", _e("r/c"), _e("r/a"))
    b: Manifest = _m("r", _e("r/b"))
    u: Manifest = Manifest.union(a, b)
    assert paths(u) == ["r/a", "r/b", "r/c"]
    assert len(a) == 2 and len(b) == 1


def test_union_same_root_is_kept() -> None:
    assert Manifest.union(_m("r", _e("r/a")), _m("r", _e("r/b"))).root == "r"


def test_union_different_roots_uses_common_ancestor() -> None:
    u: Manifest = Manifest.union(_m("/x/a", _e("/x/a/f")), _m("/x/b", _e("/x/b/g")))
    assert u.root == "/x"


def test_union_mixed_relative_and_absolute_roots_use_abspath() -> None:
    u: Manifest = Manifest.union(_m("sub", _e("sub/f")), _m(os.getcwd(), _e("g")))
    assert u.root == os.path.abspath(os.getcwd())


def test_union_explicit_root_wins() -> None:
    u: Manifest = Manifest.union(_m("/x/a"), _m("/x/b"), root="/custom")
    assert u.root == "/custom"


def test_union_single_manifest_returns_equal_manifest() -> None:
    m: Manifest = _m("r", _e("r/a"))
    assert Manifest.union(m) == m


def test_union_without_arguments_raises() -> None:
    with pytest.raises(ValueError):
        Manifest.union()


def test_union_without_arguments_but_with_root_is_empty() -> None:
    u: Manifest = Manifest.union(root="r")
    assert u.root == "r" and len(u) == 0


def test_union_deduplicates_by_path_earliest_argument_wins() -> None:
    first: ManifestEntry = _e("x", "1")
    second: ManifestEntry = _e("x", "2")
    third: ManifestEntry = _e("x", "3")
    u: Manifest = Manifest.union(
        _m("r", first), _m("r", second, _e("y")), _m("r", third)
    )
    assert paths(u) == ["x", "y"]
    assert u.entries[0] is first


def test_or_operator_is_union() -> None:
    a: Manifest = _m("r", _e("x", "mine"))
    b: Manifest = _m("r", _e("x", "theirs"), _e("y"))
    u: Manifest = a | b
    assert u == Manifest.union(a, b)
    assert u.entries[0].sha256 == "mine"


def test_or_with_non_manifest_is_not_supported() -> None:
    with pytest.raises(TypeError):
        _m("r") | 1  # type: ignore[operator]


# --- diff -------------------------------------------------------------------


def test_diff_of_identical_manifests_is_empty() -> None:
    m: Manifest = _m("r", _e("r/a"))
    d: ManifestDiff = m.diff(m)
    assert isinstance(d, ManifestDiff)
    assert all(len(part) == 0 for part in d)


def test_diff_classifies_removed_added_changed() -> None:
    old: Manifest = _m("r", _e("r/gone"), _e("r/same"), _e("r/mod", "1"))
    new: Manifest = _m("r", _e("r/same"), _e("r/mod", "2"), _e("r/fresh"))
    d: ManifestDiff = old.diff(new)
    assert paths(d.removed) == ["r/gone"]
    assert paths(d.added) == ["r/fresh"]
    assert [e.sha256 for e in d.changed_before] == ["1"]
    assert [e.sha256 for e in d.changed_after] == ["2"]


def test_diff_compares_absolute_paths() -> None:
    old: Manifest = _m("/a", _e("/a/sub/f"))
    new: Manifest = _m("/b", _e("/b/sub/f"))
    d: ManifestDiff = old.diff(new)
    assert paths(d.removed) == ["/a/sub/f"]
    assert paths(d.added) == ["/b/sub/f"]
    assert len(d.changed_before) == len(d.changed_after) == 0


def test_diff_result_manifests_carry_their_side_root() -> None:
    d: ManifestDiff = _m("old", _e("old/a")).diff(_m("new", _e("new/b")))
    assert d.removed.root == "old" and d.added.root == "new"
    assert d.changed_before.root == "old" and d.changed_after.root == "new"


def test_diff_ignores_mtime_but_detects_size_hash_and_error_changes() -> None:
    old: Manifest = _m("r", _e("r/t", mtime=1.0), _e("r/s", size=1), _e("r/e"))
    err: ManifestEntry = ManifestEntry("r/e", None, None, error="ERROR: x")
    new: Manifest = _m("r", _e("r/t", mtime=99.0), _e("r/s", size=2), err)
    assert paths(old.diff(new).changed_before) == ["r/e", "r/s"]


def test_diff_changed_sides_are_parallel_and_sorted() -> None:
    old: Manifest = _m("o", _e("o/b", "1"), _e("o/a", "1"))
    new: Manifest = _m("n", _e("n/a", "2"), _e("n/b", "2"))
    d: ManifestDiff = old.diff_relative_root(new)
    assert paths(d.changed_before) == ["o/a", "o/b"]
    assert paths(d.changed_after) == ["n/a", "n/b"]


def test_diff_is_directional() -> None:
    a: Manifest = _m("r", _e("r/x"))
    b: Manifest = _m("r", _e("r/y"))
    assert paths(a.diff(b).removed) == ["r/x"]
    assert paths(b.diff(a).added) == ["r/x"]


# --- diff_relative_root -----------------------------------------------------


def test_diff_relative_root_matches_across_roots_using_manifest_roots() -> None:
    old: Manifest = _m("/a", _e("/a/sub/f", "1"), _e("/a/gone"), _e("/a/same"))
    new: Manifest = _m("/b", _e("/b/sub/f", "2"), _e("/b/fresh"), _e("/b/same"))
    d: ManifestDiff = old.diff_relative_root(new)
    assert paths(d.removed) == ["/a/gone"]
    assert paths(d.added) == ["/b/fresh"]
    assert paths(d.changed_before) == ["/a/sub/f"]
    assert paths(d.changed_after) == ["/b/sub/f"]
    assert d.removed.root == "/a" and d.added.root == "/b"


def test_diff_relative_root_explicit_roots_override_manifest_roots() -> None:
    old: Manifest = _m("/x", _e("/x/a/f"), _e("/x/a/g"))
    new: Manifest = _m("/x", _e("/x/b/f", "2"), _e("/x/b/h"))
    d: ManifestDiff = old.diff_relative_root(new, self_root="/x/a", other_root="/x/b")
    assert paths(d.removed) == ["/x/a/g"]
    assert paths(d.added) == ["/x/b/h"]
    assert paths(d.changed_after) == ["/x/b/f"]


def test_diff_relative_root_only_one_root_overridden() -> None:
    old: Manifest = _m("/x", _e("/x/a/f"))
    new: Manifest = _m("/b", _e("/b/f"))
    d: ManifestDiff = old.diff_relative_root(new, self_root="/x/a")
    assert all(len(part) == 0 for part in d)


def test_diff_relative_root_same_root_equals_diff() -> None:
    old: Manifest = _m("r", _e("r/a", "1"), _e("r/b"))
    new: Manifest = _m("r", _e("r/a", "2"), _e("r/c"))
    assert old.diff_relative_root(new) == old.diff(new)
