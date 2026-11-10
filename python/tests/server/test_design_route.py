"""Design route: advisory next weight and indicator, read-only."""

# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app


def _client(tmp_path: Path) -> TestClient:
    labs = LabRegistry()
    labs.register(register())
    c = TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs)))
    assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code in (200, 201)
    return c


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/server/routes/design.py::make_design_router
def test_next_weight_cold_start(tmp_path: Path) -> None:
    """With no points the route suggests the lightest load and says cold start."""
    c = _client(tmp_path)
    body = c.get("/api/design/next-weight").json()
    assert body["advisory"] is True
    assert body["suggestion"]["unit"] == "kg"
    assert "cold_start" in body["indicator"]["reasons"]
    assert body["indicator"]["n"] == 0


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/server/routes/design.py::make_design_router
def test_next_weight_is_read_only(tmp_path: Path) -> None:
    """Asking for advice does not change the recorded points."""
    c = _client(tmp_path)
    before = c.get("/api/session/points").json()
    c.get("/api/design/next-weight")
    assert c.get("/api/session/points").json() == before


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
            phase="load",
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
