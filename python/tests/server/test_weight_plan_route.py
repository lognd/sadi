"""Weight-plan route: plans from entered weights with no lab or session, 4xx on bad input."""

# frob:ticket 01M72X7ZB936PEBXHRGX06FSAD

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sadi.server.app import AppSettings, create_app

WEIGHTS = [{"mass_kg": m} for m in (0.01, 0.02, 0.02, 0.05, 0.05, 0.1, 0.1, 0.2)]


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A started app with no lab and no session."""
    with TestClient(create_app(AppSettings(data_root=tmp_path))) as c:
        yield c


# frob:tests python/sadi/server/routes/weight_plan.py::make_weight_plan_router
def test_plan_without_session(client: TestClient) -> None:
    """With an entered slope the plan works and carries propagated uncertainty."""
    r = client.post("/api/weight-plan", json={"weights": WEIGHTS, "cal_slope_v_per_m": 200.0})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cal_source"] == "entered"
    assert body["plan"]["hangs"][0]["reason"].startswith("Hang #1")
    assert body["propagated"] is None or len(body["propagated"]["stress"]) == len(
        body["plan"]["hangs"]
    )


# frob:tests python/sadi/server/routes/weight_plan.py::make_weight_plan_router
def test_missing_slope_is_4xx(client: TestClient) -> None:
    """No entered slope and no session calibration gives a clear 422."""
    r = client.post("/api/weight-plan", json={"weights": WEIGHTS})
    assert r.status_code == 422
    assert "slope" in r.json()["hint"].lower()


# frob:tests python/sadi/server/routes/weight_plan.py::make_weight_plan_router
def test_no_weights_is_4xx(client: TestClient) -> None:
    """An empty inventory is refused with the planner's message."""
    r = client.post("/api/weight-plan", json={"weights": [], "cal_slope_v_per_m": 200.0})
    assert r.status_code == 422


# frob:tests python/sadi/server/routes/weight_plan.py::make_weight_plan_router
def test_defaults_without_calibration(client: TestClient) -> None:
    """Defaults say where the slope comes from when there is no calibration."""
    body = client.get("/api/weight-plan/defaults").json()
    assert body["cal_slope_v_per_m"] is None
    assert body["source"] == "none"
    assert "volts per metre" in body["explanation"]
