"""Weight-plan persistence: append-only inventory events and replanning from captured points."""

# frob:ticket 01M72YENT6PZMVDMYGZ2BWDNK9

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app

WEIGHTS = [{"mass_kg": m} for m in (0.01, 0.02, 0.02, 0.05, 0.05, 0.1, 0.1, 0.2)]
BODY = {"weights": WEIGHTS, "cal_slope_v_per_m": 200.0}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A started app with one open lctt session."""
    labs = LabRegistry()
    labs.register(register())
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code in (200, 201)
        yield c


# frob:tests python/sadi/server/routes/weight_plan.py::make_weight_plan_router
def test_save_is_append_only_and_deduplicated(client: TestClient) -> None:
    """Each changed save appends an event; history is kept; identical re-saves write nothing."""
    first = client.post("/api/weight-plan/inventory", json=BODY)
    assert first.status_code == 201 and first.json()["appended"] is True
    again = client.post("/api/weight-plan/inventory", json=BODY)
    assert again.json() == {"seq": None, "appended": False, "events": 1}
    edited = {**BODY, "weights": [*WEIGHTS, {"mass_kg": 0.5}]}
    third = client.post("/api/weight-plan/inventory", json=edited)
    assert third.json()["appended"] is True and third.json()["seq"] > first.json()["seq"]
    got = client.get("/api/weight-plan/inventory").json()
    assert got["events"] == 2
    assert len(got["latest"]["weights"]) == 9


# frob:tests python/sadi/server/routes/weight_plan.py::make_weight_plan_router
def test_save_without_session_is_4xx(tmp_path: Path) -> None:
    """With no open session nothing can be saved and the problem says so."""
    with TestClient(create_app(AppSettings(data_root=tmp_path))) as c:
        assert c.post("/api/weight-plan/inventory", json=BODY).status_code == 409


# frob:tests python/sadi/server/routes/weight_plan.py::make_weight_plan_router
def test_next_without_saved_inventory_is_404(client: TestClient) -> None:
    """Replanning needs a saved inventory."""
    r = client.get("/api/weight-plan/next")
    assert r.status_code == 404


# frob:tests python/sadi/server/routes/weight_plan.py::make_weight_plan_router
def test_next_replans_from_captured_points(client: TestClient) -> None:
    """The next hang moves past the captured load once points are captured."""
    client.post("/api/weight-plan/inventory", json=BODY)
    first = client.get("/api/weight-plan/next").json()
    assert first["captured"] == 0 and first["next_hang"] is not None
    for st in ("setup", "calibrate", "tare"):
        assert client.post("/api/session/wizard/skip", json={"step": st}).status_code == 200
    for i, m in enumerate([0.05, 0.1]):
        pt = {
            "phase": "elastic",
            "inputs": {"volts": 0.1 * m + 0.001 * i, "mass_kg": m},
            "window": {"first_raw_seq": i, "last_raw_seq": i},
            "settled": True,
            "forced_early": False,
        }
        assert client.post("/api/session/points", json=pt).status_code in (200, 201)
    after = client.get("/api/weight-plan/next").json()
    assert after["captured"] == 2
    assert after["next_hang"] is not None
    assert after["next_hang"]["total_mass_kg"] > 0.1 + 1e-9
