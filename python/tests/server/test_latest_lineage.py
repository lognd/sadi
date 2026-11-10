"""mark_latest/newer_than follow parent lineage, not version numbers (audit3 M5)."""

# frob:ticket 01M727965F98C8FB295P7A7FRS

from __future__ import annotations

from sadi.server.routes.sessions import mark_latest, newer_than
from sadi.server.schemas import SessionSummary


def _s(v: int, parent: int | None, state: str = "closed") -> SessionSummary:
    """A summary for version `v` of family `f` whose parent is version `parent`."""
    return SessionSummary(
        name=f"f-v{v:03d}",
        family="f",
        version=v,
        lab="lctt",
        state=state,
        parent=None if parent is None else f"f-v{parent:03d}",
    )


# frob:tests python/sadi/server/routes/sessions.py::mark_latest
def test_branch_from_old_version_does_not_supersede_newer_work() -> None:
    """v003 branched from v001 leaves v002 as a latest leaf; v001 is superseded."""
    out = {i.name: i for i in mark_latest([_s(1, None), _s(2, 1), _s(3, 1)])}
    assert out["f-v001"].latest is False
    assert out["f-v002"].latest is True
    assert out["f-v003"].latest is True


# frob:tests python/sadi/server/routes/sessions.py::mark_latest
def test_incomplete_child_neither_supersedes_nor_is_latest() -> None:
    """A failed-fold child leaves its parent as the latest."""
    out = {i.name: i for i in mark_latest([_s(1, None), _s(2, 1, "incomplete")])}
    assert out["f-v001"].latest is True
    assert out["f-v002"].latest is True  # incomplete rows are left unflagged, never steer away


# frob:tests python/sadi/server/routes/sessions.py::newer_than
def test_newer_than_is_descendants_only() -> None:
    """Only complete descendants count as newer."""
    items = [_s(1, None), _s(2, 1), _s(3, 1), _s(4, 2), _s(5, 4, "incomplete")]
    assert sorted(newer_than(items, "f-v001")) == ["f-v002", "f-v003", "f-v004"]
    assert newer_than(items, "f-v003") == []
    assert newer_than(items, "f-v004") == []
    assert newer_than(items, "nope") == []
