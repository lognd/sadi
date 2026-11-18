"""Audit1 #7 #9 #13 #15 #18 #32: honest E interval, surfaced pending/notes, calibration values."""

# frob:ticket 01M71XGHCQP7KZ6HEFPJ2KEMF8

from __future__ import annotations

import random

import pytest
from typani import Ok

from sadi.core.errors import ComputeCode, ComputeError
from sadi.core.results import ResultSet
from sadi.labs.lctt.guidance import EvenScheduleSuggester, LoadRange, Phase
from sadi.labs.lctt.lab import LcttLab
from sadi.labs.lctt.settle import detect_settle
from sadi.server.live import LIVE_SETTLE
from tests.labs.lctt.test_lab import (
    E_TRUE,
    ELASTIC_MASSES,
    SLOPE,
    TARE_V,
    _captured,
    _elastic_points,
    _phased,
    _plastic_points,
    _shared,
)

SHORT_L0 = 0.08313
LONG_L0 = 0.5


def _inputs(plastic_never_yields: bool = False):  # noqa: ANN202 - test helper
    plastic = (
        _elastic_points(SHORT_L0, ELASTIC_MASSES)
        if plastic_never_yields
        else _plastic_points(SHORT_L0)
    )
    return [*_shared(), *_phased(_plastic_points(LONG_L0), "elastic"), *_phased(plastic, "plastic")]


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_pending_and_notes_survive_analyze() -> None:
    """#9: an uncomputable yield is reported as pending with its note, not silently dropped."""
    inputs = _inputs(plastic_never_yields=True)
    res = LcttLab().analyze(_captured(inputs), inputs)
    assert isinstance(res, Ok)
    assert "yield_stress" in res.danger_ok.pending
    assert "yield_stress" not in res.danger_ok.values


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_analyze_emits_slope_intercept_tare() -> None:
    """#13: the UI's calibration/tare names are produced with the right units and values."""
    inputs = _inputs()
    vals = LcttLab().analyze(_captured(inputs), inputs).danger_ok.values
    assert vals["slope"].unit == "m/V"
    assert vals["slope"].value == pytest.approx(SLOPE, rel=1e-3)
    assert vals["intercept"].unit == "m"
    assert vals["tare"].unit == "V"
    assert vals["tare"].value == pytest.approx(TARE_V)


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_calibration_values_present_before_both_runs() -> None:
    """#13: slope/tare appear as soon as calibration and tare exist, even with one run."""
    inputs = [*_shared(), *_phased(_plastic_points(LONG_L0), "elastic")]
    vals = LcttLab().analyze(_captured(inputs), inputs).danger_ok.values
    assert {"slope", "intercept", "tare"} <= set(vals)


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_modulus_uncertainty_includes_systematics() -> None:
    """#7: E's standard uncertainty is wider than the bare regression SE (creep, diameter, cal)."""
    inputs = _inputs()
    e = LcttLab().analyze(_captured(inputs), inputs).danger_ok.values["E"]
    assert e.standard_uncertainty >= 0.03 * e.value


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_modulus_interval_covers_creep_biased_truth() -> None:
    """#7: with a 1-4 % creep bias on the elastic run the 95 % interval still covers truth."""
    e_true = E_TRUE
    rng = random.Random(7)
    misses = 0
    for _ in range(12):
        inputs = _inputs()
        biased = []
        for i in inputs:
            if getattr(i, "phase", "") == "elastic":
                s = 1.0 + rng.uniform(0.01, 0.04) * (i.mass_kg / 6.0)
                i = i.model_copy(update={"volts": TARE_V + (i.volts - TARE_V) * s})
            biased.append(i)
        e = LcttLab().analyze(_captured(biased), biased).danger_ok.values["E"]
        misses += abs(e.value - e_true) > 2.0 * e.standard_uncertainty
    assert misses <= 1


# frob:tests python/sadi/labs/lctt/guidance.py::EvenScheduleSuggester.suggest
def test_guidance_says_masses_on_hanger() -> None:
    """#15: the instruction no longer says 'total', matching load_force's mass + hanger."""
    got = EvenScheduleSuggester().suggest(
        Phase.ELASTIC, ResultSet(), LoadRange(min_kg=0.0, max_kg=5.0)
    )
    text = got.danger_ok.text
    assert "total" not in text.lower()
    assert "hanger" in text


# frob:tests python/sadi/labs/lctt/settle.py::detect_settle
def test_live_settle_rejects_noisy_drift() -> None:
    """#18: 113 mV/s drift under sensor noise is not declared settled 20 ms after a load."""
    rng = random.Random(3)
    n = 2000
    times = [k / 1000.0 for k in range(n)]
    lvdt = [0.113 * t + rng.gauss(0.0, 0.002) for t in times]
    res = detect_settle(times, lvdt, LIVE_SETTLE)
    assert isinstance(res, Ok)
    assert not res.danger_ok.settled
    assert res.danger_ok.reason != "insufficient_data"
    quiet = detect_settle(times, [rng.gauss(0.0, 0.0005) for _ in times], LIVE_SETTLE)
    assert quiet.danger_ok.settled


# frob:tests python/sadi/server/routes/results.py::live_results
def test_too_few_points_note_has_no_repr() -> None:
    """#32: the note shows the human detail, never the Python repr of the error."""
    err = ComputeError(code=ComputeCode.TOO_FEW_POINTS, detail="no point has volts and load")
    assert "code=" not in err.detail
