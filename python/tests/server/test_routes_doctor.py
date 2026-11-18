"""Tests for the doctor routes via FastAPI TestClient."""

# frob:ticket 01M6WKJKCYJ3PQG2DEX16R80J2

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sadi.doctor.registry import all_checks
from sadi.server.routes_doctor import make_doctor_router


@pytest.fixture(scope="module")
def client() -> TestClient:
    app = FastAPI()
    app.include_router(make_doctor_router())
    return TestClient(app)


# frob:tests python/sadi/server/routes_doctor.py::make_doctor_router
def test_list_ok_and_shape(client: TestClient) -> None:
    r = client.get("/api/doctor")
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == 1
    assert body["summary"]["verdict"] in {"ready", "degraded", "blocked"}
    assert len(body["results"]) == len(all_checks())
    for key in ("id", "title", "layer", "severity", "status", "headline", "duration_ms"):
        assert key in body["results"][0]


# frob:tests python/sadi/server/routes_doctor.py::make_doctor_router
def test_single_run_ok(client: TestClient) -> None:
    check_id = all_checks()[0][0].id
    r = client.post(f"/api/doctor/{check_id}/run")
    assert r.status_code == 200
    assert r.json()["id"] == check_id


# frob:tests python/sadi/server/routes_doctor.py::make_doctor_router
@pytest.mark.parametrize("bad", ["ZZZ-999", "nope"])
def test_unknown_id_404(client: TestClient, bad: str) -> None:
    r = client.post(f"/api/doctor/{bad}/run")
    assert r.status_code == 404
    assert "detail" in r.json()


# frob:ticket 01M72D3CTDED2MGDY721RSM8M4
# frob:tests python/sadi/server/routes_doctor.py::make_doctor_router
def test_single_run_never_probes_device(monkeypatch: pytest.MonkeyPatch) -> None:
    from sadi.server import routes_doctor

    seen = []
    real = routes_doctor.run

    def spy(opts):  # type: ignore[no-untyped-def]
        seen.append(opts)
        return real(opts)

    monkeypatch.setattr(routes_doctor, "run", spy)
    app = FastAPI()
    app.include_router(make_doctor_router())
    check_id = all_checks()[0][0].id
    assert TestClient(app).post(f"/api/doctor/{check_id}/run").status_code == 200
    assert seen and seen[0].probe_device is False
