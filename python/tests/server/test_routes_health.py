"""Tests for GET /api/health."""

# frob:ticket 01M6WZZEHBSPSCHA90KQG3RK1T

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sadi.server.app import create_app
from sadi.server.routes_health import make_health_router


# frob:tests python/sadi/server/routes_health.py::make_health_router
def test_health_ok_without_session() -> None:
    """Health answers 200 on a fresh app with no session open."""
    r = TestClient(create_app()).get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["version"], str) and body["version"]
    assert body["simulated"] is None


# frob:tests python/sadi/server/routes_health.py::make_health_router
def test_health_reports_sim_flag() -> None:
    """The optional simulated callable is surfaced in the payload."""
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(make_health_router(lambda: True))
    assert TestClient(app).get("/api/health").json()["simulated"] is True


# frob:ticket 01M72YAG3BHTR584JK3TY2DE40
# frob:tests python/sadi/server/routes_health.py::make_health_router
def test_health_reports_data_root_without_running_doctor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Health carries the data folder and never invokes the full doctor run."""
    import sadi.doctor as doctor

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("doctor run must not be used for the data folder")

    monkeypatch.setattr(doctor, "run", boom)
    app = FastAPI()
    app.include_router(make_health_router(data_root=tmp_path))
    assert TestClient(app).get("/api/health").json()["data_root"] == str(tmp_path)
