"""Tests for the LCTT creep fit on synthetic log-time creep holds."""

# frob:ticket 01M6W7R1N7W6ZKBBM4M7NDJSG8

from __future__ import annotations

import math
import random

import pytest
from pydantic import ValidationError
from typani import Err, Ok

from sadi.labs.lctt.creep import CreepConfig, CreepError, CreepFit, fit_creep

T_LOAD = 100.0


def _times(n: int = 60, dt: float = 5.0) -> list[float]:
    return [T_LOAD + (i + 1) * dt for i in range(n)]


def _fit(
    t: list[float], y: list[float], t_ref: float = 1e4, cfg: CreepConfig | None = None
) -> CreepFit:
    res = fit_creep(t, y, T_LOAD, t_ref, cfg)
    assert isinstance(res, Ok)
    return res.danger_ok


def _err(t: list[float], y: list[float], t_ref: float = 1e4) -> CreepError:
    res = fit_creep(t, y, T_LOAD, t_ref)
    assert isinstance(res, Err)
    return res.danger_err


# frob:tests python/sadi/labs/lctt/creep.py::fit_creep
def test_exact_log_law_recovered() -> None:
    t = _times()
    y = [1e-4 + 2e-5 * math.log(x - T_LOAD) for x in t]
    f = _fit(t, y)
    assert f.b.value == pytest.approx(2e-5, rel=1e-9)
    assert f.a.value == pytest.approx(1e-4, rel=1e-9)
    assert f.r2 == pytest.approx(1.0)
    assert f.n_points == 60
    assert f.strain_at_ref.value == pytest.approx(1e-4 + 2e-5 * math.log(1e4 - T_LOAD))


# frob:tests python/sadi/labs/lctt/creep.py::fit_creep
def test_injected_slope_recovered_within_noise() -> None:
    # simulator law: amp * ln(1 + dt/tau); for dt >> tau the ln-slope is amp
    amp, tau = 3e-5, 1.0
    rng = random.Random(7)
    t = _times(200, 2.0)
    y = [amp * math.log(1 + (x - T_LOAD) / tau) + rng.gauss(0, 2e-6) for x in t]
    f = _fit(t, y)
    assert abs(f.b.value - amp) < 3 * f.b.std_unc + 0.02 * amp
    assert f.b.std_unc > 0
    assert f.r2 > 0.99
    assert f.b.dof == 198


# frob:tests python/sadi/labs/lctt/creep.py::fit_creep
def test_extrapolation_uncertainty_grows_with_distance() -> None:
    rng = random.Random(3)
    t = _times()
    y = [1e-4 + 2e-5 * math.log(x - T_LOAD) + rng.gauss(0, 1e-6) for x in t]
    near = _fit(t, y, t_ref=t[-1]).strain_at_ref.std_unc
    far = _fit(t, y, t_ref=1e7).strain_at_ref.std_unc
    assert far > near > 0


# frob:tests python/sadi/labs/lctt/creep.py::fit_creep
def test_short_hold_typed_error() -> None:
    t = _times(4)
    assert _err(t, [0.0, 1.0, 2.0, 3.0]) is CreepError.HoldTooShort
    t2 = [T_LOAD + 10.0 + i * 0.1 for i in range(10)]  # under half a decade
    assert _err(t2, [float(i) for i in range(10)]) is CreepError.HoldTooShort


# frob:tests python/sadi/labs/lctt/creep.py::fit_creep
def test_bad_inputs_typed_errors() -> None:
    t = _times(10)
    y = [float(i) for i in range(10)]
    assert _err(t, y[:5]) is CreepError.LengthMismatch
    assert _err(t, [math.nan, *y[1:]]) is CreepError.NonFinite
    assert _err([t[1], t[0], *t[2:]], y) is CreepError.NonMonotonicTime
    assert _err([T_LOAD, *t[1:]], y) is CreepError.BeforeLoad
    assert _err(t, y, t_ref=T_LOAD) is CreepError.BadReference


# frob:tests python/sadi/labs/lctt/creep.py::CreepConfig
def test_config_frozen_and_validated() -> None:
    with pytest.raises(ValidationError):
        CreepConfig(min_points=2)
    with pytest.raises(ValidationError):
        CreepConfig().min_points = 9  # ty: ignore[invalid-assignment]


# frob:tests python/sadi/labs/lctt/creep.py::CreepFit
def test_fit_exposes_plot_and_decision_inputs() -> None:
    t = _times()
    f = _fit(t, [2e-5 * math.log(x - T_LOAD) for x in t])
    again = CreepFit.model_validate_json(f.model_dump_json())
    assert again.b.value == f.b.value and again.t_ref == f.t_ref
    assert f.b.interval95().is_ok
    assert f.strain_at_ref.unit == f.b.unit
