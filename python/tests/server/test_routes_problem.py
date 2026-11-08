"""Errors from the REST routes are problem+json with a what-to-do hint."""

# frob:ticket 01M6W7R3XY1B0BF689RX3H80G2

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the lctt lab over a tmp data root."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        yield c


def _assert_problem(res: Response, status: int) -> dict[str, Any]:
    assert res.status_code == status, res.text
    assert res.headers["content-type"].startswith("application/problem+json")
    body = res.json()
    assert body["status"] == status and body["hint"] and body["type"]
    return body


# frob:tests python/sadi/server/routes/problem.py::render
# frob:tests python/sadi/server/routes/problem.py::unwrap
# frob:tests python/sadi/server/routes/problem.py::conflict
# frob:tests python/sadi/server/service.py::SessionService.wizard_state
def test_no_open_session_is_409_with_hint(client: TestClient) -> None:
    """Calls needing a session answer 409 telling the operator to create one."""
    body = _assert_problem(client.get("/api/session/wizard"), 409)
    assert "session" in body["hint"].lower()


# frob:tests python/sadi/server/routes/problem.py::from_sadi
# frob:tests python/sadi/server/routes/problem.py::not_found
def test_unknown_lab_and_session(client: TestClient) -> None:
    """Unknown lab is an input problem; unknown session name is 404."""
    _assert_problem(client.post("/api/sessions", json={"lab": "nope"}), 422)
    _assert_problem(client.post("/api/sessions/resume", json={"name": "ghost"}), 404)
    _assert_problem(client.post("/api/sessions/resume", json={"name": "../x"}), 404)


# frob:tests python/sadi/server/routes/problem.py::from_wizard
# frob:tests python/sadi/server/service.py::SessionService.complete
def test_bad_capture_and_wizard_errors(client: TestClient) -> None:
    """Missing inputs are 422; capture on a non-capture step and wizard misuse map to problems."""
    client.post("/api/sessions", json={"lab": "lctt"})
    bad = {"phase": "calibration", "inputs": {}, "window": {"first_raw_seq": 1, "last_raw_seq": 2}}
    _assert_problem(client.post("/api/session/points", json=bad), 422)
    _assert_problem(client.post("/api/session/wizard/complete", json={"step": "tare"}), 409)
    _assert_problem(client.post("/api/session/points/none/edit", json={"op": "exclude"}), 404)
    _assert_problem(client.post("/api/session/undo"), 409)


# frob:tests python/sadi/server/routes/problem.py::install_problem_handlers
def test_validation_errors_are_problem_json(client: TestClient) -> None:
    """Malformed bodies (extra field) are 422 problem+json, not FastAPI's default shape."""
    _assert_problem(client.post("/api/sessions", json={"lab": "lctt", "bogus": 1}), 422)
