"""Tests for POST /api/stress-strain/fit: contract shape, typed 4xx errors, read-only."""

# frob:ticket 01M6WMSZKN488HTWG19V69GETD

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from fastapi.testclient import TestClient
from typani import Err, Ok

from sadi.labs.lctt.modulus import CurvePoint
from sadi.server.app import AppSettings, create_app
from sadi.server.routes_stress_strain import CurveSource, RefitError
from sadi.uncertainty import Measured

E_PA = 70e9


def _curve(n: int = 8) -> list[CurvePoint]:
    pts = []
    for i in range(n):
        eps = 0.0005 * (i + 1)
        sigma = E_PA * eps + 1e6 + (1e3 if i % 2 else -1e3)
        s = Measured.create(sigma, 1e5, "Pa").danger_ok
        e = Measured.create(eps, 1e-6, "").danger_ok
        pts.append(CurvePoint(index=i, stress=s, strain=e))
    return pts


def _client(source: CurveSource | None, tmp_path: Path) -> TestClient:
    return TestClient(create_app(AppSettings(data_root=tmp_path, curve_source=source)))


def test_fit_returns_client_view(tmp_path: Path) -> None:
    """A valid window yields every ModulusFitView field in the client's units."""
    # frob:tests python/sadi/server/routes_stress_strain.py::to_view
    # frob:tests python/sadi/server/routes_stress_strain.py::refit
    # frob:tests python/sadi/server/routes_stress_strain.py::make_stress_strain_router
    pts = _curve()
    c = _client(lambda: Ok(pts), tmp_path)
    res = c.post("/api/stress-strain/fit", json={"first": 1, "last": 6})
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {
        "first",
        "last",
        "modulusMpa",
        "interceptMpa",
        "display",
        "eGpa",
        "eU95Gpa",
        "r2",
        "lowR2",
    }
    assert (body["first"], body["last"]) == (1, 6)
    assert abs(body["eGpa"] - 70.0) < 1.0
    assert abs(body["modulusMpa"] - body["eGpa"] * 1000) < 1e-6
    assert body["eU95Gpa"] > 0
    assert 0.99 < body["r2"] <= 1.0
    assert body["lowR2"] is False
    assert "GPa" in body["display"]


def test_bad_window_is_typed_422(tmp_path: Path) -> None:
    """A window under 3 points returns 422 with error/detail the client can show."""
    # frob:tests python/sadi/server/routes_stress_strain.py::refit
    # frob:tests python/sadi/server/routes_stress_strain.py::make_stress_strain_router
    pts = _curve()
    c = _client(lambda: Ok(pts), tmp_path)
    for win in ({"first": 2, "last": 3}, {"first": 5, "last": 2}, {"first": 0, "last": 99}):
        res = c.post("/api/stress-strain/fit", json=win)
        assert res.status_code == 422
        assert res.json()["error"] == "BadWindow"
        assert res.json()["detail"]


def test_missing_body_fields_rejected(tmp_path: Path) -> None:
    """A malformed body is a 4xx."""
    # frob:tests python/sadi/server/routes_stress_strain.py::make_stress_strain_router
    res = _client(lambda: Ok(_curve()), tmp_path).post("/api/stress-strain/fit", json={"first": 1})
    assert res.status_code == 422


def test_no_data_is_409(tmp_path: Path) -> None:
    """With no source, or a source that fails, the endpoint answers a typed 409."""
    # frob:tests python/sadi/server/routes_stress_strain.py::make_stress_strain_router
    for src in (None, lambda: Err(RefitError.NoData)):
        res = _client(src, tmp_path).post("/api/stress-strain/fit", json={"first": 0, "last": 4})
        assert res.status_code == 409
        assert res.json()["error"] == "NoData"


def test_fit_is_read_only(tmp_path: Path) -> None:
    """Repeated fits leave the source data and data root contents unchanged."""
    # frob:tests python/sadi/server/routes_stress_strain.py::refit
    # frob:tests python/sadi/server/routes_stress_strain.py::make_stress_strain_router
    pts: Sequence[CurvePoint] = _curve()
    before = list(pts)
    with TestClient(create_app(AppSettings(data_root=tmp_path, curve_source=lambda: Ok(pts)))) as c:
        names = sorted(p.name for p in tmp_path.iterdir())
        a = c.post("/api/stress-strain/fit", json={"first": 0, "last": 5}).json()
        b = c.post("/api/stress-strain/fit", json={"first": 0, "last": 5}).json()
        assert sorted(p.name for p in tmp_path.iterdir()) == names
    assert a == b
    assert list(pts) == before
