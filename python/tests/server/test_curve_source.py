"""Tests for the active-session CurveSource wired into create_app (read-only)."""

# frob:ticket 01M6WMXEM0M76VKMN2WF3C3VYD

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.server.app import AppSettings, create_app
from sadi.server.curve_source import active_session, load_curve, make_curve_source
from sadi.server.routes_stress_strain import RefitError
from sadi.store.events import PointV1, PointWindow, point_record
from sadi.store.records import NewRecord
from sadi.store.session import SessionMeta, create_session
from sadi.store.writer_thread import WriterHandle

K = 1.0e-3  # m per volt


def _pt(phase: str, **inputs: float) -> NewRecord:
    """Build a POINT record for `phase` with raw `inputs`."""
    p = PointV1(phase=phase, window=PointWindow(first_raw_seq=1, last_raw_seq=1), inputs=inputs)
    return point_record(p)


def _record_session(root: Path, n: int = 8) -> Path:
    """Create a session with cal, tare, specimen and `n` load points; return its dir."""
    h = create_session(root, SessionMeta(slug="ss")).danger_ok
    w = WriterHandle.open(h.path / "wal", uuid.uuid4(), 1).danger_ok
    recs = [_pt("calibration", volts=float(v), height=0.08 + K * v) for v in range(5)]
    recs += [_pt("tare", mean=0.0, sd=0.001, n=100)]
    recs += [_pt("specimen", diameter=0.005, u_diameter=1e-6, hanger_kg=0.1)]
    recs += [
        _pt("load", volts=0.01 * (i + 1) + (1e-4 if i % 2 else 0), mass_kg=1.0 * (i + 1))
        for i in range(n)
    ]
    for r in recs:
        assert w.submit(r).is_ok
    assert w.close().is_ok
    return h.path


def _tree_digest(root: Path) -> str:
    """Hash every file's relative path, size and bytes under `root`."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode() + p.read_bytes())
    return h.hexdigest()


def test_no_session_is_no_data(tmp_path: Path) -> None:
    """With no sessions the offline loader says NoData; the endpoint says no open session."""
    # frob:tests python/sadi/server/curve_source.py::load_curve
    # frob:tests python/sadi/server/curve_source.py::active_session
    # frob:tests python/sadi/server/curve_source.py::make_curve_source
    assert active_session(tmp_path) is None
    assert load_curve(tmp_path).danger_err is RefitError.NoData
    c = TestClient(create_app(AppSettings(data_root=tmp_path)))
    res = c.post("/api/stress-strain/fit", json={"first": 0, "last": 3})
    assert res.status_code == 409
    assert res.json()["error"] == "NoOpenSession"


def test_active_session_feeds_fit_read_only(tmp_path: Path) -> None:
    """create_app serves a fit from the supplied session path and leaves the data untouched."""
    # frob:tests python/sadi/server/app.py::create_app
    # frob:tests python/sadi/server/curve_source.py::load_curve
    sdir = _record_session(tmp_path)
    assert active_session(tmp_path) == sdir
    before = _tree_digest(sdir)
    curve = load_curve(tmp_path).danger_ok
    assert len(curve) == 8
    source = make_curve_source(lambda: sdir)
    c = TestClient(
        create_app(AppSettings(data_root=tmp_path, require_root_lock=False, curve_source=source))
    )
    res = c.post("/api/stress-strain/fit", json={"first": 1, "last": 6})
    assert res.status_code == 200, res.text
    assert res.json()["modulusMpa"] > 0
    assert _tree_digest(sdir) == before


# frob:ticket 01M72D3CTDED2MGDY721RSM8M4
def test_refit_curve_uses_elastic_rows_only(tmp_path: Path) -> None:
    """The plastic run is another specimen: it never enters the curve the E refit sees."""
    # frob:tests python/sadi/server/curve_source.py::load_session_curve
    h = create_session(tmp_path, SessionMeta(slug="ph")).danger_ok
    w = WriterHandle.open(h.path / "wal", uuid.uuid4(), 1).danger_ok
    recs = [_pt("calibration", volts=float(v), height=0.08 + K * v) for v in range(5)]
    recs += [_pt("tare", mean=0.0, sd=0.001, n=100)]
    recs += [_pt("specimen", diameter=0.005, u_diameter=1e-6, hanger_kg=0.1)]
    recs += [_pt("elastic", volts=0.01 * (i + 1), mass_kg=float(i + 1)) for i in range(5)]
    recs += [_pt("plastic", volts=0.02 * (i + 1), mass_kg=float(i + 1)) for i in range(4)]
    for r in recs:
        assert w.submit(r).is_ok
    assert w.close().is_ok
    curve = load_curve(tmp_path).danger_ok
    assert len(curve) == 5
