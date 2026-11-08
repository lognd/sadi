"""Settle meta (settled, forced_early, drift, t_since_load_s) survives the WAL and recover_state."""

# frob:ticket 01M6WNNMJX4MDX9TBZZ6Q18K2C
from __future__ import annotations

import uuid
from pathlib import Path

from sadi.core.point_inputs import LoadInputs, PointMeta, build_point, parse_meta
from sadi.store.events import PointV1, PointWindow, point_record, recover_state
from sadi.store.session import SessionMeta, create_session
from sadi.store.writer_thread import WriterHandle

_WIN = PointWindow(first_raw_seq=1, last_raw_seq=9)
_IN = LoadInputs(volts=0.5, mass_kg=2.0)


def _replay(root: Path, points: list[PointV1]) -> list[PointV1]:
    """Write the points to a fresh WAL and return them as recovered."""
    h = create_session(root, SessionMeta(slug="meta")).danger_ok
    w = WriterHandle.open(h.path / "wal", uuid.uuid4(), 1).danger_ok
    for p in points:
        assert w.submit(point_record(p)).is_ok  # type: ignore[arg-type]
    assert w.close().is_ok
    state = recover_state(h.path)
    assert state.is_ok
    return [cp.point for cp in state.danger_ok.view().points]


def test_flags_round_trip_through_recover_state(tmp_path: Path) -> None:
    """Forced-early and settled points keep every flag after replay."""
    forced = PointMeta(t_since_load_s=12.5, drift_rate=-1e-5, settled=False, forced_early=True)
    settled = PointMeta(t_since_load_s=40.0, drift_rate=2e-7, settled=True, forced_early=False)
    out = _replay(tmp_path, [build_point(_IN, _WIN, forced), build_point(_IN, _WIN, settled)])
    assert [parse_meta(p) for p in out] == [forced, settled]


def test_legacy_point_without_meta_parses(tmp_path: Path) -> None:
    """A POINT with no meta fields reads as defaults."""
    legacy = PointV1(phase="load", window=_WIN, inputs={"volts": 0.1, "mass_kg": 1.0})
    (p,) = _replay(tmp_path, [legacy])
    assert parse_meta(p) == PointMeta()
    assert build_point(_IN, _WIN).settled is False
