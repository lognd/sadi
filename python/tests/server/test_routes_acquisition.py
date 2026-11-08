"""Tests for POST /api/session/load-change."""

# frob:ticket 01M6X1GGD923K25M13JM84ZB2J
from __future__ import annotations

from fastapi.testclient import TestClient
from typani import Err, Ok, Result

from sadi.core.pipeline import PipelineError
from sadi.server.app import create_app
from sadi.server.live import LiveError
from sadi.server.routes.acquisition import make_acquisition_router, mark_load_change


# frob:tests python/sadi/server/routes/acquisition.py::make_acquisition_router
def test_load_change_409_without_live_session() -> None:
    """No live acquisition wired: a 409 problem with a hint, nothing raised."""
    r = TestClient(create_app()).post("/api/session/load-change")
    assert r.status_code == 409
    assert r.json()["type"].endswith("no_live_session")
    assert r.json()["hint"]


# frob:tests python/sadi/server/routes/acquisition.py::make_acquisition_router
def test_load_change_ok_returns_marker_seq() -> None:
    """A live run's marker seq is returned and the changer is called once."""
    from fastapi import FastAPI

    from sadi.server.routes.problem import install_problem_handlers

    calls: list[int] = []

    def changer() -> Result[int, object]:
        calls.append(1)
        return Ok(42)

    app = FastAPI()
    install_problem_handlers(app)
    app.include_router(make_acquisition_router(changer))
    r = TestClient(app).post("/api/session/load-change")
    assert r.status_code == 200
    assert r.json() == {"marker_seq": 42}
    assert calls == [1]


# frob:tests python/sadi/server/routes/acquisition.py::mark_load_change
def test_mark_load_change_maps_refusals() -> None:
    """Live, halted and missing-changer refusals map to 409 problems."""
    assert mark_load_change(lambda: Err(LiveError.NoLiveSession)).danger_err.status == 409
    assert mark_load_change(lambda: Err(PipelineError.Halted)).danger_err.status == 409
    assert mark_load_change(None).danger_err.status == 409


# frob:tests python/sadi/server/live.py::LiveAcquisition.mark_load_change
def test_live_mark_load_change_without_run() -> None:
    """With no run started LiveAcquisition refuses with NoLiveSession."""
    from typing import cast

    from sadi.core.device import DeviceService
    from sadi.core.pipeline import Bus
    from sadi.server.live import LiveAcquisition

    live = LiveAcquisition(cast("DeviceService", object()), Bus())
    assert live.mark_load_change() == Err(LiveError.NoLiveSession)
