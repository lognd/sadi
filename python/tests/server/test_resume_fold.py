"""Resume folds the parent's points and wizard state into the child WAL; parent untouched."""

# frob:ticket 01M6WTCAA5WR1VD7H7ES7757MP

from __future__ import annotations

import hashlib
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
    """App with the lctt lab over a tmp data root."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        yield c


def _digest(d: Path) -> dict[str, str]:
    """Map every file under `d` to its sha256."""
    return {
        str(p.relative_to(d)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(d.rglob("*"))
        if p.is_file()
    }


def _capture(c: TestClient) -> dict[str, Any]:
    body = {"phase": "calibration", "inputs": {"volts": 1.0, "height": 0.01}, "window": WINDOW}
    res = c.post("/api/session/points", json=body)
    assert res.status_code == 201, res.text
    return res.json()


# frob:tests python/sadi/server/service.py::SessionService.resume
# frob:tests python/sadi/server/service.py::_fold_parent
def test_resume_folds_points_and_wizard(client: TestClient, tmp_path: Path) -> None:
    """The child sees the parent's points, edits, wizard position; the parent is unchanged."""
    first = client.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).json()
    assert client.post("/api/session/wizard/skip", json={"step": "setup"}).status_code == 200
    _capture(client)
    pid = client.get("/api/session/points").json()[0]["point_id"]
    edit = client.post(f"/api/session/points/{pid}/edit", json={"op": "exclude", "args": {}})
    assert edit.status_code == 200
    client.post("/api/session/close")
    parent_dir = tmp_path / "sessions" / first["name"]
    before = _digest(parent_dir)
    want = client.get("/api/sessions").json()
    assert want

    res = client.post("/api/sessions/resume", json={"name": first["name"]})
    assert res.status_code == 201, res.text
    pts = client.get("/api/session/points").json()
    assert [p["point_id"] for p in pts] == [pid]
    assert pts[0]["excluded"] is True
    assert client.get("/api/session/wizard").json()["current"] == "calibrate"
    # new work lands after the folded records
    cap = _capture(client)
    assert cap["seq"] > 3
    client.post("/api/session/close")

    assert _digest(parent_dir) == before
    child = recover_state(tmp_path / "sessions" / res.json()["name"]).danger_ok
    assert len(child.points) == 2 and len(child.edits) == 1


# frob:tests python/sadi/server/service.py::SessionService.list_sessions
# frob:tests python/sadi/server/service.py::SessionService.resume
def test_versions_grouped_latest_marked_and_old_resume_warns(client: TestClient) -> None:
    """Audit1 #12: the newest version is marked; resuming an older one reports newer work."""
    v1 = client.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).json()["name"]
    client.post("/api/session/close")
    v2 = client.post("/api/sessions/resume", json={"name": v1}).json()
    assert v2["newer_versions"] == []
    client.post("/api/session/close")
    listed = {s["name"]: s for s in client.get("/api/sessions").json()}
    assert listed[v2["name"]]["latest"] is True
    assert listed[v1]["latest"] is False and listed[v1]["latest_name"] == v2["name"]
    v3 = client.post("/api/sessions/resume", json={"name": v1}).json()
    assert v3["newer_versions"] == [v2["name"]]
    client.post("/api/session/close")
