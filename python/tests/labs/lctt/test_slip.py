"""Tests for the LCTT slip detector on seeded synthetic creep holds and the slip fixture."""

# frob:ticket 01M6W7R257EXZX1RD7VT3M5GJG

from __future__ import annotations

import csv
import json
import math
import random
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from typani import Err, Ok, Result

from sadi.labs.lctt.slip import (
    SlipConfig,
    SlipError,
    SlipReport,
    detect_slip,
    noise_floor_for_lsb,
    slip_config_from_adc,
)

T_LOAD = 100.0
SIGMA = 2e-6
FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "short_slip"
# Documented bounds: steps of >= MIN_STEP (15 sigma) are always found; <= FP_BOUND of
# slip-free noise holds may raise any event.
MIN_STEP = 15 * SIGMA
FP_BOUND = 0.01


def _hold(
    rng: random.Random, steps: dict[int, float], n: int = 120, amp: float = 2e-4
) -> tuple[list[float], list[float]]:
    """Creep hold amp*ln(1+dt/tau) + white noise + step jumps at given sample indices."""
    t = [T_LOAD + (i + 1) * 5.0 for i in range(n)]
    y = [amp * math.log(1 + (v - T_LOAD) / 20.0) + rng.gauss(0, SIGMA) for v in t]
    for idx, size in steps.items():
        for j in range(idx, n):
            y[j] += size
    return t, y


def _ok(res: Result[SlipReport, SlipError]) -> SlipReport:
    assert isinstance(res, Ok)
    return res.danger_ok


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
def test_pure_creep_has_no_events() -> None:
    t, y = _hold(random.Random(1), {})
    assert _ok(detect_slip(t, y, T_LOAD)).events == ()


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
def test_step_reported_with_time_size_confidence() -> None:
    t, y = _hold(random.Random(2), {60: 5e-5})
    (ev,) = _ok(detect_slip(t, y, T_LOAD)).events
    assert ev.index == 60 and ev.time == t[60]
    assert ev.size == pytest.approx(5e-5, rel=0.1)
    assert 0.99 < ev.confidence <= 1.0


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
def test_strong_creep_is_not_slip() -> None:
    t, y = _hold(random.Random(3), {}, amp=5e-3)
    assert _ok(detect_slip(t, y, T_LOAD)).events == ()


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
def test_load_change_is_not_slip() -> None:
    t, y = _hold(random.Random(4), {60: 5e-5})
    load = [50.0 if i < 60 else 60.0 for i in range(len(t))]
    cfg = SlipConfig(load_tol=1.0)
    assert _ok(detect_slip(t, y, T_LOAD, load=load, config=cfg)).events == ()


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
def test_min_size_filters_small_steps() -> None:
    t, y = _hold(random.Random(5), {60: 3e-5})
    assert len(_ok(detect_slip(t, y, T_LOAD)).events) == 1
    assert _ok(detect_slip(t, y, T_LOAD, config=SlipConfig(min_size=1e-4))).events == ()


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
def test_detects_all_injected_steps_and_bounds_false_positives() -> None:
    missed = false_pos = 0
    for seed in range(300):
        rng = random.Random(1000 + seed)
        idx = rng.randrange(15, 105)
        size = rng.choice([-1, 1]) * rng.uniform(MIN_STEP, 10 * MIN_STEP)
        t, y = _hold(rng, {idx: size})
        events = _ok(detect_slip(t, y, T_LOAD)).events
        if not any(abs(e.index - idx) <= 1 for e in events):
            missed += 1
        false_pos += sum(1 for e in events if abs(e.index - idx) > 1)
        t, y = _hold(random.Random(5000 + seed), {})
        false_pos += bool(_ok(detect_slip(t, y, T_LOAD)).events)
    assert missed == 0
    assert false_pos / 600 <= FP_BOUND


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
def test_slip_fixture_flags_documented_rows() -> None:
    exp = json.loads((FIXTURES / "expected.json").read_text())
    with (FIXTURES / "short_slip.csv").open() as fh:
        rows = list(csv.DictReader(fh))
    t = [float(r["t_s"]) for r in rows]
    y = [float(r["strain"]) for r in rows]
    load = [float(r["load_n"]) for r in rows]
    report = _ok(detect_slip(t, y, exp["t_load"], load=load))
    assert [e.index for e in report.events] == [s["index"] for s in exp["slips"]]
    for ev, s in zip(report.events, exp["slips"], strict=True):
        assert ev.time == s["time"]
        assert ev.size == pytest.approx(s["size"], rel=0.15)


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
@pytest.mark.parametrize(
    ("kwargs", "err"),
    [
        ({"strain": [0.0] * 29}, SlipError.LengthMismatch),
        ({"strain": [0.0] * 29 + [math.nan]}, SlipError.NonFinite),
        (
            {"times": [float(i) + 101 for i in (0, 1, 1) + tuple(range(3, 30))]},
            SlipError.NonMonotonicTime,
        ),
        ({"t_load": 200.0}, SlipError.BeforeLoad),
        ({"times": [101.0, 102.0], "strain": [0.0, 0.0]}, SlipError.TooShort),
    ],
)
def test_bad_input_errors(kwargs: dict[str, object], err: SlipError) -> None:
    args: dict[str, Any] = {
        "times": [101.0 + i for i in range(30)],
        "strain": [0.0] * 30,
        "t_load": T_LOAD,
    }
    args.update(kwargs)
    res = detect_slip(**args)
    assert isinstance(res, Err) and res.danger_err == err


# frob:tests python/sadi/labs/lctt/slip.py::SlipConfig
def test_config_frozen_and_validated() -> None:
    with pytest.raises(ValidationError):
        SlipConfig(window=1)
    with pytest.raises(ValidationError):
        SlipConfig().window = 3  # ty: ignore[invalid-assignment]  # frozen model: assignment must raise


LSB_V = 2 * 5.12 / 2**16
STRAIN_PER_V = 0.05


def _quantised(steps: dict[int, float]) -> tuple[list[float], list[float]]:
    """Near-constant hold quantised to ADC codes with 1-LSB flicker, plus optional steps."""
    t = [T_LOAD + 1 + i * 0.1 for i in range(120)]
    codes = [(i % 7 == 0) + (i % 11 == 0) for i in range(120)]
    y = [
        STRAIN_PER_V * LSB_V * (c + sum(v for k, v in steps.items() if i >= k))
        for i, c in enumerate(codes)
    ]
    return t, y


# frob:ticket 01M6Z5X8ABWY83TMY0ETZBMN5W
# frob:tests python/sadi/labs/lctt/slip.py::slip_config_from_adc
def test_derived_floor_suppresses_lsb_flicker_but_keeps_glitch() -> None:
    """With the one-LSB floor a quantised hold has no events and a 26-LSB step is found."""
    cfg_r = slip_config_from_adc(5.12, STRAIN_PER_V)
    assert cfg_r.is_ok
    cfg = cfg_r.danger_ok
    assert cfg.noise_floor == pytest.approx(STRAIN_PER_V * LSB_V)
    t, y = _quantised({})
    assert _ok(detect_slip(t, y, T_LOAD, config=cfg)).events == ()
    t, y = _quantised({60: 26.0})
    (ev,) = _ok(detect_slip(t, y, T_LOAD, config=cfg)).events
    assert 58 <= ev.index <= 62


# frob:ticket 01M6Z5X8ABWY83TMY0ETZBMN5W
# frob:tests python/sadi/labs/lctt/slip.py::noise_floor_for_lsb
def test_noise_floor_for_lsb_rejects_bad_input() -> None:
    """Non-positive full scale, zero gain and zero bits are errors, not silent floors."""
    assert noise_floor_for_lsb(0.0, 1.0).is_err
    assert noise_floor_for_lsb(5.12, 0.0).is_err
    assert noise_floor_for_lsb(5.12, 1.0, bits=0).is_err
    assert noise_floor_for_lsb(5.12, -2.0).danger_ok == pytest.approx(2 * 2 * 5.12 / 2**16)
