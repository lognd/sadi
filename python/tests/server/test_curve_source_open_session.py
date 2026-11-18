"""The stress-strain refit must use the open session, never the newest-named session dir."""

# frob:ticket 01M726PZNXA6BEXH97TQPK3176

from __future__ import annotations

import logging
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.store.events import PointV1, PointWindow, point_record
from sadi.store.records import NewRecord
from sadi.store.session import SessionMeta, create_session
from sadi.store.writer_thread import WriterHandle

_log = logging.getLogger(__name__)
FIT = {"first": 1, "last": 6}


def _pt(phase: str, **inputs: float) -> NewRecord:
    """Build a POINT record for `phase` with raw `inputs`."""
    p = PointV1(phase=phase, window=PointWindow(first_raw_seq=1, last_raw_seq=1), inputs=inputs)
    return point_record(p)


def _record(root: Path, slug: str, slope: float) -> Path:
    """Write a closed session whose load points have stress/strain slope proportional to `slope`."""
    h = create_session(root, SessionMeta(slug=slug, lab_module="lctt")).danger_ok
    w = WriterHandle.open(h.path / "wal", uuid.uuid4(), 1).danger_ok
    recs = [_pt("calibration", volts=float(v), height=0.08 + 1.0e-3 * v) for v in range(5)]
    recs += [_pt("tare", mean=0.0, sd=0.001, n=100)]
    recs += [_pt("specimen", diameter=0.005, u_diameter=1e-6, hanger_kg=0.1)]
    recs += [
        _pt("load", volts=0.01 * (i + 1) + (1e-4 if i % 2 else 0), mass_kg=slope * (i + 1))
        for i in range(8)
    ]
    for r in recs:
        assert w.submit(r).is_ok
    assert w.close().is_ok
    assert h.close().is_ok
    return h.path


@contextmanager
def _client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the lctt lab over `tmp_path` (sessions are written first, then the app starts)."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        yield c


# frob:tests python/sadi/server/curve_source.py::make_curve_source
# frob:tests python/sadi/server/curve_source.py::SessionReplayCache.curve
# frob:tests python/sadi/server/app.py::create_app
def test_refit_uses_open_session_not_newest_name(tmp_path: Path) -> None:
    """Family A (older, sorts first) is resumed; the refit must reflect A, not newer family B."""
    a = _record(tmp_path, "wire1", slope=1.0)
    b = _record(tmp_path, "wire2", slope=3.0)
    assert a.name < b.name  # the resumed family sorts before the newer one
    with _client(tmp_path) as client:
        assert client.post("/api/sessions/resume", json={"name": b.name}).status_code == 201
        e_b = client.post("/api/stress-strain/fit", json=FIT).json()["modulusMpa"]
        assert client.post("/api/session/close").status_code == 204
        assert client.post("/api/sessions/resume", json={"name": a.name}).status_code == 201
        res = client.post("/api/stress-strain/fit", json=FIT)
    assert res.status_code == 200, res.text
    e_a = res.json()["modulusMpa"]
    _log.info("fit E_a=%s E_b=%s", e_a, e_b)
    assert e_b > 1.5 * e_a  # B carries 3x the load per step; A's refit must not show B's data


# frob:tests python/sadi/server/curve_source.py::make_curve_source
def test_refit_without_open_session_is_409(tmp_path: Path) -> None:
    """Closed sessions exist on disk, but with none open the refit answers 409 NoOpenSession."""
    _record(tmp_path, "wire1", slope=1.0)
    with _client(tmp_path) as client:
        res = client.post("/api/stress-strain/fit", json=FIT)
    assert res.status_code == 409
    body = res.json()
    assert body["error"] == "NoOpenSession"
    assert "no_open_session" in body["detail"]
