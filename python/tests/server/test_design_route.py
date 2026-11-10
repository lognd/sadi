"""Design route: advisory next weight and indicator, read-only."""

# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """A started app (closed on teardown) with one open lctt session."""
    labs = LabRegistry()
    labs.register(register())
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code in (200, 201)
        yield c


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/server/routes/design.py::make_design_router
def test_next_weight_cold_start(client: TestClient) -> None:
    """With no points the route suggests the lightest load and says cold start."""
    body = client.get("/api/design/next-weight").json()
    assert body["advisory"] is True
    assert body["suggestion"]["unit"] == "kg"
    assert "cold_start" in body["indicator"]["reasons"]
    assert body["indicator"]["n"] == 0


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/server/routes/design.py::make_design_router
def test_next_weight_is_read_only(client: TestClient) -> None:
    """Asking for advice does not change the recorded points."""
    before = client.get("/api/session/points").json()
    client.get("/api/design/next-weight")
    assert client.get("/api/session/points").json() == before


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/server/routes/design.py::design_obs
def test_design_obs_filters_unsettled_and_excluded() -> None:
    """Only active settled (or force-accepted) load points become observations."""
    from sadi.design.models import DesignPhase
    from sadi.server.routes.design import design_obs
    from sadi.server.schemas import PointView

    def pv(i: int, **kw: object) -> PointView:
        base = dict(
            point_id=f"p{i}",
            seq=i,
            phase="elastic",
            excluded=False,
            inputs={"volts": 1.0, "mass_kg": i},
            window=None,
            history=[],
            settled=False,
            forced_early=False,
        )
        base.update(kw)
        return PointView.model_construct(**base)

    views = [
        pv(1, settled=True),
        pv(2),
        pv(3, settled=True, excluded=True),
        pv(4, forced_early=True),
    ]
    assert [o.x for o in design_obs(views, DesignPhase.ELASTIC)] == [1.0, 4.0]


def _post_points(client: TestClient, phase: str, masses: list[float], k: float = 0.1) -> None:
    """Capture settled points of `phase` through the real POST route."""
    for i, m in enumerate(masses):
        body = {
            "phase": phase,
            "inputs": {"volts": k * m + 0.001 * i, "mass_kg": m},
            "window": {"first_raw_seq": i, "last_raw_seq": i},
            "settled": True,
            "forced_early": False,
        }
        assert client.post("/api/session/points", json=body).status_code in (200, 201)


def _skip(client: TestClient) -> None:
    for st in ("setup", "calibrate", "tare"):
        assert client.post("/api/session/wizard/skip", json={"step": st}).status_code == 200


# frob:ticket 01M72T4QZQQABVKR5PX78KV8YS
# frob:ticket 01M72VM5TYFDN445BY0W9G68B1
# frob:tests python/sadi/server/routes/design.py::design_obs
def test_elastic_points_via_post_reach_selector(client: TestClient) -> None:
    """Points captured as phase 'elastic' count toward the elastic advice."""
    _skip(client)
    _post_points(client, "elastic", [0.5, 1.0, 1.5, 2.0, 2.5])
    body = client.get("/api/design/next-weight?phase=elastic").json()
    assert body["indicator"]["n"] == 5


# frob:ticket 01M72T4QZQQABVKR5PX78KV8YS
# frob:ticket 01M72VM5TYFDN445BY0W9G68B1
# frob:tests python/sadi/server/routes/design.py::offset_volts
def test_yield_without_calibration_has_null_suggestion(client: TestClient) -> None:
    """Yield advice with no offset source returns a null suggestion and a reason."""
    body = client.get("/api/design/next-weight?phase=yield").json()
    assert body["suggestion"] is None
    assert "no_elastic_fit" in body["indicator"]["reasons"]
    _skip(client)
    _post_points(client, "elastic", [0.5, 1.0, 1.5, 2.0])
    body = client.get("/api/design/next-weight?phase=yield").json()
    assert body["suggestion"] is None
    assert "no_calibration" in body["indicator"]["reasons"]


# frob:ticket 01M72T4QZQQABVKR5PX78KV8YS
# frob:ticket 01M72VM5TYFDN445BY0W9G68B1
# frob:tests python/sadi/server/routes/design.py::offset_volts
def test_yield_counts_plastic_points_only(client: TestClient) -> None:
    """Yield advice counts only plastic points (a different specimen) and suggests a real load."""
    _skip(client)
    _post_points(client, "elastic", [0.5, 1.0, 1.5, 2.0])
    assert client.post("/api/session/wizard/complete", json={"step": "elastic"}).status_code == 200
    _post_points(client, "plastic", [2.5, 3.0])
    body = client.get("/api/design/next-weight?phase=yield&offset=0.01").json()
    assert body["indicator"]["n"] == 2
    assert body["suggestion"] is not None
