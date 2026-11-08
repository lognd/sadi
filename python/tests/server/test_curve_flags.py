"""Settle flags on replayed LoadPoint events (carried from WAL POINT meta)."""

# frob:ticket 01M6WP144S0ENPQESCQEQ6NT5Y

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from sadi.labs.lctt.live import LoadPoint
from sadi.server.curve_source import session_events
from sadi.store.events import PointV1, PointWindow, point_record
from sadi.store.session import SessionMeta, create_session
from sadi.store.writer_thread import WriterHandle


def _record(root: Path, points: list[PointV1]) -> Path:
    """Write `points` to a fresh session WAL; return the session dir."""
    h = create_session(root, SessionMeta(slug="fl")).danger_ok
    w = WriterHandle.open(h.path / "wal", uuid.uuid4(), 1).danger_ok
    for p in points:
        assert w.submit(point_record(p)).is_ok
    assert w.close().is_ok
    return h.path


def _load(**kw: Any) -> PointV1:
    """Build a load POINT with optional settle meta."""
    return PointV1(
        phase="load",
        window=PointWindow(first_raw_seq=1, last_raw_seq=1),
        inputs={"volts": 0.1, "mass_kg": 1.0},
        **kw,
    )


def test_flags_reach_load_point(tmp_path: Path) -> None:
    """Forced-early, settled and drift meta appear on the replayed LoadPoint events."""
    # frob:tests python/sadi/server/curve_source.py::session_events
    # frob:tests python/sadi/server/curve_source.py::_event
    sdir = _record(
        tmp_path,
        [
            _load(forced_early=True, drift_rate=0.5, t_since_load_s=3.0),
            _load(settled=True),
        ],
    )
    res = session_events(sdir)
    assert res.is_ok
    pts = [e for e in res.danger_ok if isinstance(e, LoadPoint)]
    assert len(pts) == 2
    assert pts[0].forced_early and not pts[0].settled
    assert pts[0].drift_rate == 0.5 and pts[0].t_since_load_s == 3.0
    assert pts[1].settled and not pts[1].forced_early


def test_legacy_point_defaults(tmp_path: Path) -> None:
    """A POINT without meta yields a LoadPoint with default flags."""
    # frob:tests python/sadi/server/curve_source.py::session_events
    sdir = _record(tmp_path, [_load()])
    pts = [e for e in session_events(sdir).danger_ok if isinstance(e, LoadPoint)]
    assert not pts[0].forced_early and not pts[0].settled
    assert pts[0].drift_rate is None and pts[0].t_since_load_s is None
