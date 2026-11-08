"""Tests for the shared session-point projections."""

# frob:ticket 01M6WVADCSP63DBMYH3RNCXWTM

from __future__ import annotations

from types import SimpleNamespace

from sadi.server.schemas import PointView
from sadi.server.session_points import active_points, to_captured


def _view(excluded: bool, first: int, last: int) -> PointView:
    """Build a minimal PointView stand-in."""
    return PointView.model_construct(
        excluded=excluded,
        window=SimpleNamespace(first_sample=first, last_sample=last),
    )


# frob:tests python/sadi/server/session_points.py::active_points
def test_active_points_drops_excluded() -> None:
    """Excluded points are filtered out."""
    views = [_view(False, 0, 5), _view(True, 6, 9)]
    assert active_points(views) == [views[0]]


# frob:tests python/sadi/server/session_points.py::to_captured
def test_to_captured_reindexes_and_clamps_window() -> None:
    """Indices restart at zero and window end never precedes start."""
    out = to_captured([_view(False, 4, 2), _view(False, 5, 9)])
    assert [c.index for c in out] == [0, 1]
    assert out[0].window.end == 4.0
    assert out[1].window.end == 9.0
