"""Tests for the LCTT clamp-slip check on clean and slipping simulated cycles."""

# frob:ticket 01M6W7R2TPG1HC0F9QHDQ1C3W6

from __future__ import annotations

import math
import random

from typani import Err, Ok

from sadi.labs.lctt.clamp_check import (
    ADVICE_RETIGHTEN,
    SETUP_STEP_ID,
    ClampCheckConfig,
    ClampCheckError,
    ClampCycle,
    check_clamp_slip,
    setup_subcheck,
)

SIGMA = 2e-6


def _cycle(
    rng: random.Random, step: float = 0.0, drift: float = 0.0, t_load: float = 10.0
) -> ClampCycle:
    """Simulated hold: log creep + noise, optional slip step mid-hold, zero drift after."""
    t = [t_load + (i + 1) * 1.0 for i in range(30)]
    y = [1e-4 * math.log(1 + (v - t_load) / 5.0) + rng.gauss(0, SIGMA) for v in t]
    for j in range(15, 30):
        y[j] += step
    return ClampCycle(
        t_load=t_load, times=tuple(t), strain=tuple(y), zero_before=0.0, zero_after=drift
    )


# frob:tests python/sadi/labs/lctt/clamp_check.py::check_clamp_slip
def test_clean_cycles_pass() -> None:
    rng = random.Random(1)
    res = check_clamp_slip([_cycle(rng) for _ in range(3)])
    assert isinstance(res, Ok)
    assert res.value.passed
    assert all(not v.events for v in res.value.cycles)


# frob:tests python/sadi/labs/lctt/clamp_check.py::check_clamp_slip
def test_slipping_cycle_fails_with_advice() -> None:
    rng = random.Random(2)
    res = check_clamp_slip([_cycle(rng), _cycle(rng, step=5e-5), _cycle(rng)])
    assert isinstance(res, Ok)
    assert not res.value.passed
    assert res.value.advice == ADVICE_RETIGHTEN
    assert [v.passed for v in res.value.cycles] == [True, False, True]
    assert res.value.cycles[1].events


# frob:tests python/sadi/labs/lctt/clamp_check.py::check_clamp_slip
def test_zero_not_returned_fails() -> None:
    rng = random.Random(3)
    res = check_clamp_slip([_cycle(rng, drift=1e-4)])
    assert isinstance(res, Ok)
    assert not res.value.passed
    assert not res.value.cycles[0].returned
    assert not res.value.cycles[0].events


# frob:tests python/sadi/labs/lctt/clamp_check.py::check_clamp_slip
def test_return_within_tolerance_passes() -> None:
    rng = random.Random(4)
    cfg = ClampCheckConfig(return_tol=1e-3)
    res = check_clamp_slip([_cycle(rng, drift=1e-4)], cfg)
    assert isinstance(res, Ok) and res.value.passed


# frob:tests python/sadi/labs/lctt/clamp_check.py::check_clamp_slip
def test_no_cycles_is_error() -> None:
    res = check_clamp_slip([])
    assert isinstance(res, Err) and res.error == ClampCheckError.NoCycles


# frob:tests python/sadi/labs/lctt/clamp_check.py::check_clamp_slip
def test_bad_hold_and_nonfinite_zero_are_errors() -> None:
    rng = random.Random(5)
    short = ClampCycle(t_load=0.0, times=(1.0, 2.0), strain=(0.0, 0.0), zero_before=0, zero_after=0)
    res = check_clamp_slip([short])
    assert isinstance(res, Err) and res.error == ClampCheckError.BadHold
    bad = _cycle(rng).model_copy(update={"zero_after": float("nan")})
    res = check_clamp_slip([bad])
    assert isinstance(res, Err) and res.error == ClampCheckError.NonFinite


# frob:tests python/sadi/labs/lctt/clamp_check.py::setup_subcheck
def test_setup_subcheck_descriptor() -> None:
    sub = setup_subcheck(ClampCheckConfig(cycles=2, hold_s=10))
    assert sub.step_id == SETUP_STEP_ID == "setup"
    assert "10 s" in sub.guidance and "2 times" in sub.guidance
