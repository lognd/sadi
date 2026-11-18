"""Results, budgets, guidance and device-status routes over the real app and WAL."""

# frob:ticket 01M6WTCA1SET2XBYG05J73KJ11

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import LcttLab, register
from sadi.server.app import AppSettings, create_app
from sadi.server.routes.results import ResultBudget, provenance_for, to_result_budget
from sadi.server.schemas import PointView
from sadi.store.events import PointWindow
from sadi.uncertainty.budget import build_budget
from sadi.uncertainty.covariance import CovarianceRegistry
from sadi.uncertainty.measured import Measured

WINDOW = {"first_raw_seq": 1, "last_raw_seq": 5}


def _canned_budget() -> list[ResultBudget]:
    """One real budget built with sadi uncertainty code for y = 2 x."""
    x = Measured(value=3.0, std_unc=0.1, unit="1")
    reg = CovarianceRegistry()
    reg.register(x.id, x.std_unc**2)
    b = build_budget(["x"], [x], [2.0], reg)
    return [to_result_budget("y", "Y", b, "y = 2x")]


def _client(tmp_path: Path, **kw: Any) -> Iterator[TestClient]:
    """App with the lctt lab, lifespan running so the root lock is held."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs, **kw))) as c:
        yield c


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """Default app: no device, no budget source."""
    yield from _client(tmp_path)


@pytest.fixture
def budget_client(tmp_path: Path) -> Iterator[TestClient]:
    """App with an injected budget source."""
    yield from _client(tmp_path, budgets=_canned_budget)


def _open(c: TestClient) -> None:
    assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code == 201


def _cal(c: TestClient) -> None:
    assert c.post("/api/session/wizard/skip", json={"step": "setup"}).status_code == 200
    body = {"phase": "calibration", "inputs": {"volts": 1.0, "height": 0.01}, "window": WINDOW}
    assert c.post("/api/session/points", json=body).status_code == 201


# frob:tests python/sadi/server/routes/results.py::live_results
# frob:tests python/sadi/server/routes/results.py::make_results_router
def test_results_need_open_session_then_recompute(client: TestClient) -> None:
    """No session -> problem+json 409 with a hint; open -> an (empty, stub) ResultSet."""
    res = client.get("/api/results")
    assert res.status_code == 409
    assert res.json()["hint"]
    _open(client)
    _cal(client)
    body = client.get("/api/results").json()
    assert body["values"] == []
    assert body["n_points"] == 0


# frob:tests python/sadi/server/routes/results.py::provenance_for
def test_provenance_names_points_span_and_algorithm() -> None:
    """Each quantity lists the active point ids, the sample span and the lab algorithm."""
    views = [
        PointView(
            point_id=f"p{i}",
            seq=i,
            phase="load",
            excluded=False,
            inputs={},
            window=PointWindow(first_raw_seq=1, last_raw_seq=2, first_sample=a, last_sample=b),
            history=(),
        )
        for i, (a, b) in enumerate([(10, 20), (30, 45)])
    ]
    got = provenance_for("lctt", ["E"], views)
    assert len(got) == 1
    assert got[0].point_ids == ("p0", "p1")
    assert (got[0].first_sample, got[0].last_sample) == (10, 45)
    assert got[0].algorithm == "lctt.recompute"
    assert provenance_for("lctt", ["E"], [])[0].first_sample is None


# frob:tests python/sadi/server/routes/results.py::ResultsView
def test_results_wire_has_provenance_key(client: TestClient) -> None:
    """GET /api/results carries a provenance list (empty while recompute is a stub)."""
    _open(client)
    _cal(client)
    assert client.get("/api/results").json()["provenance"] == []


# frob:tests python/sadi/server/routes/results.py::to_result_budget
def test_budgets_match_web_shape(budget_client: TestClient) -> None:
    """Budgets serialize to the web ResultBudget shape; empty without a source."""
    assert budget_client.get("/api/results/budgets").status_code == 409
    _open(budget_client)
    (row,) = budget_client.get("/api/results/budgets").json()
    assert set(row) == {
        "result",
        "label",
        "total_variance",
        "total_std_unc",
        "dominant",
        "rows",
        "latex",
    }
    assert row["dominant"]["name"] == "x"
    assert row["rows"][0]["percent"] == pytest.approx(100.0)
    assert row["total_std_unc"] == pytest.approx(0.2)


# frob:tests python/sadi/server/routes/results.py::lab_budgets
def test_budgets_empty_without_hook(tmp_path: Path) -> None:
    """A lab with no budgets hook and no injected source -> an empty list, not an error."""

    class Plain(LcttLab):
        budgets = None  # type: ignore[assignment]

    labs = LabRegistry()
    assert labs.register(Plain()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        _open(c)
        assert c.get("/api/results/budgets").json() == []


# frob:tests python/sadi/server/routes/results.py::make_results_router
def test_guidance_calibration_and_bad_target(client: TestClient) -> None:
    """Guidance counts calibration points; a bad target is a 422 problem with a hint."""
    assert client.get("/api/results/guidance").status_code == 409
    _open(client)
    _cal(client)
    g = client.get("/api/results/guidance").json()
    assert g["phase"] == "calibrate"
    assert g["points_taken"] == 1
    assert g["next_action"].startswith("Record calibration point 2")
    bad = client.get("/api/results/guidance", params={"target": -1})
    assert bad.status_code == 422
    assert bad.json()["hint"]
    assert client.get("/api/results/guidance", params={"phase": "nope"}).status_code == 422


# frob:tests python/sadi/server/routes/results.py::DeviceView
def test_device_status_unattached(client: TestClient) -> None:
    """Without a device service the status is error/attached=false with a hint."""
    body = client.get("/api/device/status").json()
    assert body["attached"] is False
    assert body["status"] == "error"
    assert body["hint"]


class _FakeDevice:
    """Stand-in for DeviceService (the native sadi_py module is not needed here)."""

    status = "simulated"
    fault = None


# frob:tests python/sadi/server/routes/results.py::DeviceProbe.status
# frob:tests python/sadi/server/routes/results.py::DeviceProbe.fault
def test_device_status_attached(tmp_path: Path) -> None:
    """An attached device reports its status and no fault."""
    for c in _client(tmp_path, device=_FakeDevice()):
        body = c.get("/api/device/status").json()
        # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
        assert body.pop("provenance")["synthetic"] is False
        assert body.pop("stop_reason") is None  # frob:ticket 01M724E09H9X4DDW9ATK14JQ5C
        assert body.pop("acquisition_fault") is None
        assert body == {"status": "simulated", "attached": True, "fault": None, "hint": ""}


class _FaultedDevice:
    """A device whose status is error with a fault object."""

    status = "error"
    fault = RuntimeError("fifo overrun")


# frob:ticket 01M727TR8PNCVA3CA5ZAVFBREF
# frob:tests python/sadi/server/routes/results.py::device_status
def test_device_status_faulted_not_attached(tmp_path: Path) -> None:
    """A faulted device reports attached=false with the fault text, never healthy."""
    for c in _client(tmp_path, device=_FaultedDevice()):
        body = c.get("/api/device/status").json()
        assert body["status"] == "error"
        assert body["attached"] is False
        assert "fifo overrun" in body["fault"]


# frob:tests python/sadi/server/routes/results.py::lab_budgets
def test_budgets_from_lab_hook(client: TestClient) -> None:
    """With no injected source, the lctt lab's own budgets are served."""
    _open(client)
    rows = client.get("/api/results/budgets").json()
    assert {r["result"] for r in rows} == {"stress", "E"}
    assert all(r["rows"] and r["latex"] and r["total_std_unc"] > 0 for r in rows)
