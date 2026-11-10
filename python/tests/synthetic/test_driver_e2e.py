"""The headless driver runs the whole wizard over HTTP and recovers the ground truth."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

import re
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from sadi.synthetic.driver import DriveReport, drive_lab
from sadi.synthetic.scenario import (
    TOL_CAL_SLOPE,
    TOL_E,
    TOL_YIELD,
    ScenarioFlags,
    generate_scenario,
)

Make = Callable[..., TestClient]


# frob:tests python/sadi/synthetic/driver.py::drive_lab
# frob:tests python/sadi/synthetic/driver.py::analyse
@pytest.mark.parametrize(("seed", "slip"), [(1, False), (2, False), (3, True)])
def test_fitted_values_match_ground_truth(make_client: Make, seed: int, slip: bool) -> None:
    """E, yield and calibration slope land within the stated tolerances; provenance is synthetic."""
    c = make_client(synthetic=True)
    got = drive_lab(c, generate_scenario(seed, ScenarioFlags(slip=slip)))
    assert got.is_ok, got
    rep = got.danger_ok
    err = rep.rel_errors()
    assert rep.synthetic is True
    assert err["e"] < TOL_E
    assert err["cal_slope"] < TOL_CAL_SLOPE
    assert 80e9 < rep.e_pa < 140e9
    _check_yield(rep)


def _check_yield(rep: DriveReport) -> None:
    """Server yield is verified when present; when absent it must be reported missing."""
    if rep.yield_pa is None:
        assert rep.missing == ("yield_stress",)
    else:
        assert rep.missing == ()
        assert rep.rel_errors()["yield"] < TOL_YIELD
    t = rep.truth
    assert abs(rep.local_yield_pa - t["yield_pa"]) / t["yield_pa"] < TOL_YIELD


# frob:tests python/sadi/synthetic/driver.py::drive_lab
def test_report_uses_servers_results_not_own_refit(make_client: Make) -> None:
    """The reported E equals what GET /api/results says, not the driver's recomputation."""
    c = make_client(synthetic=True)
    got = drive_lab(c, generate_scenario(2, ScenarioFlags()))
    assert got.is_ok, got
    served = {v["name"]: v["value"] for v in c.get("/api/results").json()["values"]}
    assert got.danger_ok.e_pa == pytest.approx(served["E"])


# frob:tests python/sadi/synthetic/driver.py::drive_lab
@pytest.mark.parametrize(
    ("seed", "flag"),
    [(3, "spike"), (4, "saturation"), (17, "dropped_frames")],
)
def test_fault_scenarios_are_excluded_and_recovered(
    make_client: Make, seed: int, flag: str
) -> None:
    """Faulty points are excluded through the server and the truth is still recovered."""
    c = make_client(synthetic=True)
    sc = generate_scenario(seed, ScenarioFlags(**{flag: True}))
    got = drive_lab(c, sc)
    assert got.is_ok, got
    rep = got.danger_ok
    assert (rep.excluded > 0) == any(p.fault for p in (*sc.elastic, *sc.plastic))
    assert rep.rel_errors()["e"] < TOL_E
    _check_yield(rep)


# frob:tests python/sadi/synthetic/driver.py::drive_lab
def test_driver_does_not_log_library_chatter(
    make_client: Make, capsys: pytest.CaptureFixture[str]
) -> None:
    """A replay keeps the uncertainty library's per-value lines off stdout."""
    c = make_client(synthetic=True)
    assert drive_lab(c, generate_scenario(1, ScenarioFlags())).is_ok
    assert re.search(r"created \S+ = ", capsys.readouterr().out) is None
