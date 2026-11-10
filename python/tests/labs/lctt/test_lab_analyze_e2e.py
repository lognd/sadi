"""End-to-end LcttLab.analyze: auto E window on a curved tail and yield_stress pending state."""

# frob:ticket 01M6X0D21V3NQV4MT5Y4DX9PC3

from __future__ import annotations

import pytest
from typani import Ok

from sadi.core.point_inputs import LoadInputs, PointInputs
from sadi.labs.lctt.lab import LcttLab, events_from_inputs
from sadi.labs.lctt.live import LiveConfig, LiveEvent, LoadPoint, SetWindow, recompute
from tests.labs.lctt.test_lab import (
    E_TRUE,
    ELASTIC_MASSES,
    _captured,
    _elastic_points,
    _phased,
    _plastic_points,
    _shared,
)

LONG_L0 = 0.5
SHORT_L0 = 0.08313


def _curved_elastic() -> list[PointInputs]:
    """Long-specimen loads linear for six points then a softening tail (curved)."""
    return _plastic_points(LONG_L0)


def _inputs(plastic: list[PointInputs]) -> list[PointInputs]:
    """Calibration, tare, specimen, a curved elastic run and the given plastic run."""
    return [*_shared(), *_phased(_curved_elastic(), "elastic"), *_phased(plastic, "plastic")]


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_analyze_e_uses_auto_window_not_all_points() -> None:
    inputs = _inputs(_plastic_points(SHORT_L0))
    res = LcttLab().analyze(_captured(inputs), inputs)
    assert isinstance(res, Ok)
    vals = res.danger_ok.values
    # The auto window ignores the curved tail, so E stays near the true modulus.
    assert vals["E"].value == pytest.approx(E_TRUE, rel=0.02)
    assert vals["r2"].value > 0.999

    # An all-points fit (explicit window over every load) is biased low by the tail.
    loads = [i for i in inputs if isinstance(i, LoadInputs) and i.phase == "elastic"]
    evs = _shared_events()
    evs += [
        LoadPoint(point_id=f"e-{k}", volts=i.volts, u_volts=i.u_volts, mass_kg=i.mass_kg,
                  u_mass_kg=i.u_mass_kg)
        for k, i in enumerate(loads)
    ]  # fmt: skip
    evs.append(SetWindow(first=0, last=len(loads) - 1))
    full = recompute(evs, LiveConfig())
    assert isinstance(full, Ok)
    e_all = next(v for v in full.danger_ok.values if v.name == "E").value
    assert abs(e_all - E_TRUE) > 5 * abs(vals["E"].value - E_TRUE)
    assert vals["E"].value != pytest.approx(e_all, rel=1e-3)


def _shared_events() -> list[LiveEvent]:
    """Live events for the shared calibration, tare and specimen inputs."""
    ev = events_from_inputs([*_shared(), _elastic_points(LONG_L0, ())[0]], "x")
    return ev.danger_ok


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_analyze_yield_present_when_plastic_run_yields() -> None:
    inputs = _inputs(_plastic_points(SHORT_L0))
    vals = LcttLab().analyze(_captured(inputs), inputs).danger_ok.values
    assert vals["yield_stress"].value > 0


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_analyze_yield_omitted_when_plastic_run_never_yields() -> None:
    """Pending state: a purely elastic short run has no offset crossing, so no yield_stress
    key is returned while E and r2 (from the long run) still are."""
    inputs = _inputs(_elastic_points(SHORT_L0, ELASTIC_MASSES))
    vals = LcttLab().analyze(_captured(inputs), inputs).danger_ok.values
    assert "yield_stress" not in vals
    assert "E" in vals and "r2" in vals


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_analyze_reports_pending_and_note_when_plastic_run_missing() -> None:
    """With no plastic run, E/r2/yield_stress are pending and a note says what is missing."""
    inputs = [*_shared(), *_phased(_curved_elastic(), "elastic")]
    res = LcttLab().analyze(_captured(inputs), inputs).danger_ok
    assert "yield_stress" not in res.values
    assert set(res.pending) == {"E", "r2", "yield_stress"}
    assert any("plastic" in n for n in res.notes)
