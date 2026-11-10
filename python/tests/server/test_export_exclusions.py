"""Excluded calibration/load points reach export and plots exactly as they reach results."""

# frob:ticket 01M7230XQFMBWVCNP4NASD05SE

from __future__ import annotations

import uuid
from pathlib import Path

from sadi.labs.lctt.figure_data import calibration_data
from sadi.labs.lctt.live import CalPoint, ExcludePoint, LoadPoint
from sadi.server.curve_source import session_events
from sadi.store.events import EditV1, PointV1, PointWindow, edit_record, point_record
from sadi.store.session import SessionMeta, create_session
from sadi.store.writer_thread import WriterHandle

_WIN = PointWindow(first_raw_seq=1, last_raw_seq=1)
# (volts, height): an exact line height = 0.01 * volts, plus one wild point.
_CAL = [(1.0, 0.01), (2.0, 0.02), (3.0, 0.03), (4.0, 0.9)]


def _record(root: Path, bad_cal_excluded: bool, load_excluded: bool) -> Path:
    """Write cal points (last one wrong) and two load points; optionally exclude some."""
    h = create_session(root, SessionMeta(slug="ex")).danger_ok
    w = WriterHandle.open(h.path / "wal", uuid.uuid4(), 1).danger_ok
    cals = [
        PointV1(phase="calibration", window=_WIN, inputs={"volts": v, "height": ht})
        for v, ht in _CAL
    ]
    loads = [
        PointV1(phase="load", window=_WIN, inputs={"volts": 0.1 * i, "mass_kg": float(i)})
        for i in (1, 2)
    ]
    for p in [*cals, *loads]:
        assert w.submit(point_record(p)).is_ok
    targets = ([cals[-1].point_id] if bad_cal_excluded else []) + (
        [loads[0].point_id] if load_excluded else []
    )
    for t in targets:
        assert w.submit(edit_record(EditV1(target=t, op="exclude"))).is_ok
    assert w.close().is_ok
    return h.path


def test_excluded_cal_point_leaves_plot_fit(tmp_path: Path) -> None:
    """Excluding the wild calibration point changes the plotted fit and its points."""
    # frob:tests python/sadi/server/curve_source.py::session_events
    both = session_events(_record(tmp_path / "a", False, False)).danger_ok
    ok = session_events(_record(tmp_path / "b", True, False)).danger_ok
    assert len([e for e in both if isinstance(e, CalPoint)]) == 4
    assert len([e for e in ok if isinstance(e, CalPoint)]) == 3
    bad = calibration_data(both).fit
    good = calibration_data(ok).fit
    assert bad is not None and good is not None
    assert abs(good.slope_m_per_v - 0.01) < 1e-9
    assert abs(bad.slope_m_per_v - 0.01) > 1e-3


def test_excluded_load_point_stays_flagged(tmp_path: Path) -> None:
    """An excluded load point is still emitted (data safety) with an ExcludePoint flag."""
    # frob:tests python/sadi/server/curve_source.py::session_events
    ev = session_events(_record(tmp_path, False, True)).danger_ok
    assert len([e for e in ev if isinstance(e, LoadPoint)]) == 2
    assert len([e for e in ev if isinstance(e, ExcludePoint)]) == 1
