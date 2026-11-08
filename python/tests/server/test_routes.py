"""REST session/wizard/point routes exercised end to end with httpx against the real WAL."""

# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.store.events import recover_state

WINDOW = {"first_raw_seq": 1, "last_raw_seq": 5}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the lctt lab over a tmp data root; lifespan runs so the root lock is held."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    app = create_app(AppSettings(data_root=tmp_path, labs=labs))
    with TestClient(app) as c:
        yield c


def _create(c: TestClient) -> dict[str, Any]:
    res = c.post("/api/sessions", json={"lab": "lctt", "slug": "t"})
    assert res.status_code == 201, res.text
    return res.json()


def _capture(c: TestClient, volts: float = 1.0) -> dict[str, Any]:
    body = {
        "phase": "calibration",
        "inputs": {"volts": volts, "height": 0.01},
        "window": WINDOW,
    }
    res = c.post("/api/session/points", json=body)
    assert res.status_code == 201, res.text
    return res.json()


# frob:tests python/sadi/server/service.py::SessionService.labs
# frob:tests python/sadi/server/service.py::SessionService.create
# frob:tests python/sadi/server/service.py::SessionService.info
# frob:tests python/sadi/server/service.py::SessionService.close
# frob:tests python/sadi/server/service.py::SessionService.list_sessions
# frob:tests python/sadi/server/service.py::SessionService.shutdown
# frob:tests python/sadi/server/routes/sessions.py::make_sessions_router
def test_labs_and_session_lifecycle(client: TestClient) -> None:
    """Create, inspect, close and list a session; a second open is refused."""
    assert [x["id"] for x in client.get("/api/labs").json()] == ["lctt"]
    info = _create(client)
    assert client.get("/api/session").json()["name"] == info["name"]
    again = client.post("/api/sessions", json={"lab": "lctt"})
    assert again.status_code == 409
    assert client.post("/api/session/close").status_code == 204
    assert client.get("/api/session").status_code == 409
    assert [s["name"] for s in client.get("/api/sessions").json()] == [info["name"]]


# frob:tests python/sadi/server/service.py::SessionService.capture
# frob:tests python/sadi/server/service.py::SessionService.edit
# frob:tests python/sadi/server/service.py::SessionService.undo
# frob:tests python/sadi/server/service.py::SessionService.redo
# frob:tests python/sadi/server/service.py::SessionService.skip
# frob:tests python/sadi/server/service.py::SessionService.points
# frob:tests python/sadi/server/service.py::SessionService.history
# frob:tests python/sadi/server/schemas.py::PointView.of
def test_capture_edit_undo_redo_lose_nothing(client: TestClient, tmp_path: Path) -> None:
    """Capture, edit, undo, redo: every action is a WAL record and nothing is deleted."""
    info = _create(client)
    skipped = client.post("/api/session/wizard/skip", json={"step": "setup"})
    assert skipped.status_code == 200, skipped.text
    assert skipped.json()["wizard"]["current"] == "calibrate"
    cap = _capture(client)
    pts = client.get("/api/session/points").json()
    assert len(pts) == 1
    target = pts[0]["point_id"]
    seq0 = cap["seq"]
    edit = client.post(f"/api/session/points/{target}/edit", json={"op": "exclude", "args": {}})
    assert edit.status_code == 200, edit.text
    assert edit.json()["seq"] > seq0
    undone = client.post("/api/session/undo")
    assert undone.status_code == 200 and undone.json()["seq"] > edit.json()["seq"]
    redone = client.post("/api/session/redo")
    assert redone.status_code == 200 and redone.json()["seq"] > undone.json()["seq"]
    assert len(client.get("/api/session/points").json()) == 1
    client.post("/api/session/close")
    replay = recover_state(tmp_path / "sessions" / info["name"]).danger_ok
    assert replay.record_count == 5 and len(replay.points) == 1


# frob:tests python/sadi/server/service.py::SessionService.resume
def test_resume_creates_new_version(client: TestClient) -> None:
    """Resume opens a new version and leaves the parent untouched."""
    first = _create(client)
    client.post("/api/session/close")
    res = client.post("/api/sessions/resume", json={"name": first["name"]})
    assert res.status_code == 201, res.text
    child = res.json()
    assert child["parent"] == first["name"]
    assert child["name"] != first["name"]
    client.post("/api/session/close")
    assert len(client.get("/api/sessions").json()) == 2


def test_recover_state_reads_open_wal(client: TestClient, tmp_path: Path) -> None:
    """The WAL can be replayed while the writer is still open."""
    info = _create(client)
    assert recover_state(tmp_path / "sessions" / info["name"]).is_ok


# frob:ticket 01M6WVJ5SYGQK3ESRH7AMECWPX
# frob:tests python/sadi/server/schemas.py::PointView.of
def test_points_carry_settle_flags(client: TestClient) -> None:
    """Captured settled/forced_early flags reach the PointView wire shape."""
    _create(client)
    assert client.post("/api/session/wizard/skip", json={"step": "setup"}).status_code == 200
    for flags in ({"settled": True}, {"forced_early": True}, {}):
        body = {
            "phase": "calibration",
            "inputs": {"volts": 1.0, "height": 0.01},
            "window": WINDOW,
            **flags,
        }
        res = client.post("/api/session/points", json=body)
        assert res.status_code == 201, res.text
    pts = client.get("/api/session/points").json()
    assert [(p["settled"], p["forced_early"]) for p in pts] == [
        (True, False),
        (False, True),
        (False, False),
    ]
