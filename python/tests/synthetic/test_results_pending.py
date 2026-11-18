"""GET /api/results explains an absent yield with pending/notes; present yield has neither."""

# frob:ticket 01M720GS24E4C7S5H9H1DPD95G
from __future__ import annotations

from collections.abc import Callable

from fastapi.testclient import TestClient

from sadi.synthetic.driver import drive_lab
from sadi.synthetic.scenario import ScenarioFlags, generate_scenario

Make = Callable[..., TestClient]


# frob:tests python/sadi/server/routes/results.py::live_results
def test_results_carry_yield_stress_after_full_run(make_client: Make) -> None:
    """After a full synthetic run the endpoint serves yield_stress and no pending for it."""
    c = make_client(synthetic=True)
    assert drive_lab(c, generate_scenario(2, ScenarioFlags())).is_ok
    body = c.get("/api/results").json()
    assert "yield_stress" in {v["name"] for v in body["values"]}
    assert "yield_stress" not in body["pending"]
