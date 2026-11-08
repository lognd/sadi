"""Tests for the LCTT settle detector on synthetic LVDT traces."""

# frob:ticket 01M6W7R1KH0MVS56MX07Q9BX19

from __future__ import annotations

import math
import random

import pytest
from pydantic import ValidationError
from typani import Err, Ok

from sadi.labs.lctt.settle import (
    NotSettledReason,
    SettleConfig,
    SettleError,
    SettleResult,
    detect_settle,
)

CFG = SettleConfig(window_s=10.0, threshold=1e-3, min_dwell_s=20.0)


def _times(n: int, dt: float = 1.0) -> list[float]:
    return [i * dt for i in range(n)]


def _run(t: list[float], y: list[float], cfg: SettleConfig = CFG) -> SettleResult:
    res = detect_settle(t, y, cfg)
    assert isinstance(res, Ok)
    return res.danger_ok


# frob:tests python/sadi/labs/lctt/settle.py::detect_settle
def test_exponential_settle() -> None:
    t = _times(300)
    y = [1.0 - math.exp(-x / 15.0) for x in t]
    r = _run(t, y)
    assert r.settled
    assert r.settled_index is not None and r.confirmed_index is not None
    assert r.confirmed_index >= r.settled_index
    assert t[r.confirmed_index] - t[r.settled_index] >= CFG.min_dwell_s
    assert r.slope is not None and abs(r.slope.value) <= CFG.threshold
    assert r.reason is None


# frob:tests python/sadi/labs/lctt/settle.py::detect_settle
def test_linear_drift_never_settles() -> None:
    t = _times(300)
    y = [0.01 * x for x in t]
    r = _run(t, y)
    assert not r.settled
    assert r.reason is NotSettledReason.SlopeAboveThreshold
    assert r.slope is not None and r.slope.value == pytest.approx(0.01)


# frob:tests python/sadi/labs/lctt/settle.py::detect_settle
def test_noise_does_not_false_settle() -> None:
    rng = random.Random(1)
    t = _times(300)
    y = [0.01 * x + rng.gauss(0, 0.5) for x in t]
    assert not _run(t, y).settled


# frob:tests python/sadi/labs/lctt/settle.py::detect_settle
def test_flat_noisy_uncertain_slope() -> None:
    rng = random.Random(2)
    t = _times(200)
    y = [rng.gauss(0, 1.0) for _ in t]
    r = _run(t, y)
    assert not r.settled
    assert r.reason in (NotSettledReason.SlopeUncertain, NotSettledReason.SlopeAboveThreshold)


# frob:tests python/sadi/labs/lctt/settle.py::detect_settle
def test_too_short() -> None:
    r = _run(_times(5), [0.0] * 5)
    assert not r.settled
    assert r.reason is NotSettledReason.InsufficientData
    assert _run([], []).reason is NotSettledReason.InsufficientData


# frob:tests python/sadi/labs/lctt/settle.py::detect_settle
def test_dwell_boundary() -> None:
    # Flat from sample 0: first full window ends at t=10, so dwell 20 is met at t=30.
    y = [0.5] * 100
    t = _times(100)
    r = _run(t, y)
    assert r.settled and r.settled_index == 10 and r.confirmed_index == 30
    short = _run(t[:30], y[:30])
    assert not short.settled and short.reason is NotSettledReason.DwellNotReached


# frob:tests python/sadi/labs/lctt/settle.py::detect_settle
def test_bad_inputs() -> None:
    assert detect_settle([0.0, 1.0], [0.0], CFG) == Err(SettleError.LengthMismatch)
    assert detect_settle([0.0, math.nan], [0.0, 0.0], CFG) == Err(SettleError.NonFinite)
    assert detect_settle([1.0, 1.0], [0.0, 0.0], CFG) == Err(SettleError.NonMonotonicTime)


# frob:tests python/sadi/labs/lctt/settle.py::SettleConfig
def test_config_bounds_and_frozen() -> None:
    with pytest.raises(ValidationError):
        SettleConfig(window_s=0, threshold=1e-3, min_dwell_s=1)
    with pytest.raises(ValidationError):
        SettleConfig(window_s=1, threshold=-1, min_dwell_s=1)
    with pytest.raises(ValidationError):
        SettleConfig(window_s=1, threshold=1e-3, min_dwell_s=1, min_points=2)
    with pytest.raises(ValidationError):
        CFG.window_s = 3.0  # ty: ignore[invalid-assignment]
