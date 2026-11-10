"""Clamp-check capture, status route and its isolation from load-point results."""

# frob:ticket 01M6XA21KQE5WEXAN39683H4S9

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sadi.core.point_inputs import ClampInputs, parse_inputs
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.clamp_check import ADVICE_OK, ADVICE_RETIGHTEN, ClampCheckConfig, clamp_status
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app

WINDOW = {"first_raw_seq": 0, "last_raw_seq": 0}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the lctt lab and an open session."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code == 201
        yield c


def _cap(c: TestClient, zb: float, za: float, slips: int = 0) -> int:
    """Capture one setup cycle; returns the HTTP status."""
    inputs = {"zero_before": zb, "zero_after": za, "slip_events": slips}
    body = {"phase": "setup", "inputs": inputs, "window": WINDOW}
    return int(c.post("/api/session/points", json=body).status_code)


# frob:tests python/sadi/core/point_inputs.py::parse_inputs
def test_parse_setup_inputs() -> None:
    """Setup phase parses to ClampInputs; missing or non-finite zeros are refused."""
    ok = parse_inputs("setup", {"zero_before": 0.0, "zero_after": 1e-6, "slip_events": 2})
    assert isinstance(ok.danger_ok, ClampInputs)
    assert ok.danger_ok.slip_events == 2
    assert parse_inputs("setup", {"zero_before": 0.0}).is_err
    assert parse_inputs("setup", {"zero_before": 0.0, "zero_after": float("nan")}).is_err


# frob:tests python/sadi/labs/lctt/clamp_check.py::clamp_status
def test_clamp_status_progress_and_verdict() -> None:
    """Verdict stays None until all cycles are in; slip or zero shift fails with advice."""
    cfg = ClampCheckConfig(cycles=2)
    part = clamp_status([(0.0, 0.0, 0)], cfg)
    assert part.passed is None
    assert part.advice == ""
    assert clamp_status([(0.0, 0.0, 0), (0.0, 1e-6, 0)], cfg).advice == ADVICE_OK
    bad = clamp_status([(0.0, 0.0, 0), (0.0, 1e-3, 0)], cfg)
    assert bad.passed is False
    assert bad.advice == ADVICE_RETIGHTEN
    assert clamp_status([(0.0, 0.0, 1), (0.0, 0.0, 0)], cfg).passed is False


# frob:tests python/sadi/server/routes/clamp.py::make_clamp_router
# frob:tests python/sadi/server/routes/clamp.py::recorded_cycles
def test_capture_then_status_and_complete(client: TestClient) -> None:
    """Three captured cycles give a verdict, complete the step, and never reach results."""
    assert client.get("/api/session/clamp-check").json()["cycles"] == []
    assert _cap(client, 0.0, 0.0) == 201
    assert client.get("/api/session/clamp-check").json()["passed"] is None
    assert _cap(client, 0.0, 1e-6) == 201
    assert _cap(client, 0.0, 5e-3, 1) == 201
    body = client.get("/api/session/clamp-check").json()
    assert [c["passed"] for c in body["cycles"]] == [True, True, False]
    assert body["passed"] is False
    assert client.get("/api/results").json()["n_points"] == 0
    # frob:ticket 01M71WYRA3SN64B56Z6G13SHSE
    blocked = client.post("/api/session/wizard/complete", json={"step": "setup"})
    assert blocked.status_code == 422  # a failed clamp check cannot be completed
    done = client.post("/api/session/wizard/skip", json={"step": "setup"})
    assert done.status_code == 200
    assert len(client.get("/api/session/points").json()) == 3


def test_bad_setup_capture_refused(client: TestClient) -> None:
    """A setup capture without zeros is refused 422 and records nothing."""
    body = {"phase": "setup", "inputs": {"zero_before": 0.0}, "window": WINDOW}
    assert client.post("/api/session/points", json=body).status_code == 422
    assert client.get("/api/session/points").json() == []
