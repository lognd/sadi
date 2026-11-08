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
        phase="load",
        inputs={},
        point_id="p",
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


# frob:ticket 01M6WV1BEFANVC4BZ2S63NEPH5
# frob:tests python/sadi/server/session_points.py::to_captured
def test_to_captured_carries_time_drift_and_status() -> None:
    """Time since load, drift rate and forced-early status survive the projection."""
    view = PointView.model_construct(
        excluded=False,
        phase="load",
        inputs={},
        point_id="p",
        window=SimpleNamespace(first_sample=0, last_sample=3),
        t_since_load_s=12.5,
        drift_rate=-0.25,
        forced_early=True,
    )
    (out,) = to_captured([view])
    assert (out.t_since_load, out.drift_rate, out.forced_early) == (12.5, -0.25, True)


# frob:tests python/sadi/server/session_points.py::to_captured
def test_to_captured_carries_raw_volts_and_load() -> None:
    """Load inputs populate volts, volts_sd and load_kg; other phases leave load_kg None."""
    load = PointView.model_construct(
        excluded=False,
        phase="load",
        inputs={"volts": 2.5, "mass_kg": 1.5, "volts_sd": 0.01},
        point_id="a",
        window=SimpleNamespace(first_sample=0, last_sample=1),
    )
    tare = PointView.model_construct(
        excluded=False,
        phase="tare",
        inputs={"mean": 0.5, "sd": 0.02, "n": 5},
        point_id="b",
        window=SimpleNamespace(first_sample=0, last_sample=1),
    )
    out = to_captured([load, tare])
    assert (out[0].volts, out[0].volts_sd, out[0].load_kg) == (2.5, 0.01, 1.5)
    assert (out[1].volts, out[1].volts_sd, out[1].load_kg) == (0.5, 0.02, None)
