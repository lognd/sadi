"""The headless driver runs the whole wizard over HTTP and recovers the ground truth."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from sadi.synthetic.driver import drive_lab
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
    assert err["yield"] < TOL_YIELD
    assert err["cal_slope"] < TOL_CAL_SLOPE
    assert 80e9 < rep.e_pa < 140e9
