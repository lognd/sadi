"""Tests for the LCTT two-specimen workflow: steps, specimens and sourced combined results."""

# frob:ticket 01M6W7R3RXWS1WSH3TPXMK16Q2

from __future__ import annotations

import pytest
from typani import Err, Ok

from sadi.core.lab import LabId
from sadi.core.models import Phase
from sadi.core.point_inputs import (
    CalibrationInputs,
    LoadInputs,
    PointInputs,
    SpecimenInputs,
    TareInputs,
)
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.lab import (
    LabError,
    LcttLab,
    SpecimenRun,
    combine_runs,
    events_from_inputs,
)
from sadi.labs.lctt.specimens import (
    SpecimenError,
    SpecimenRole,
    SpecimenSpec,
    make_spec,
    with_l0,
)
from sadi.plugins import PluginRegistry
from sadi.plugins.builtin import builtin_source

SLOPE = 0.01  # m/V
TARE_V = 0.2
DIA = 0.01
E_TRUE = 70e9
AREA = 3.141592653589793 * DIA**2 / 4
G = 9.80665


def _shared(heights: tuple[float, ...] = (0.0, 0.01, 0.02, 0.03, 0.04)) -> list[PointInputs]:
    """Calibration (volts = height / slope, with tiny noise) and one tare block."""
    cal: list[PointInputs] = [
        CalibrationInputs(volts=h / SLOPE, height=h + (1e-7 if i % 2 else -1e-7))
        for i, h in enumerate(heights)
    ]
    return [*cal, TareInputs(mean=TARE_V, sd=0.001, n=50)]


def _elastic_points(l0: float, masses: tuple[float, ...]) -> list[PointInputs]:
    """Elastic loads on a wire of modulus E_TRUE and gauge length l0."""
    out: list[PointInputs] = [SpecimenInputs(diameter=DIA, u_diameter=1e-5)]
    for m in masses:
        strain = m * G / AREA / E_TRUE
        volts = TARE_V + strain * l0 / SLOPE
        out.append(LoadInputs(volts=volts, mass_kg=m, u_volts=1e-4, u_mass_kg=1e-4))
    return out


ELASTIC_MASSES = (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)


def _plastic_points(l0: float) -> list[PointInputs]:
    """Linear for six loads, then softening so the 0.2 % offset line is crossed."""
    pts = _elastic_points(l0, ELASTIC_MASSES)
    for k, m in enumerate((7.0, 8.0, 9.0), start=1):
        strain = m * G / AREA / E_TRUE + 0.004 * k**2
        pts.append(LoadInputs(volts=TARE_V + strain * l0 / SLOPE, mass_kg=m, u_volts=1e-4))
    return pts


def _runs(
    long_l0: float | None = None, masses: tuple[float, ...] = ELASTIC_MASSES
) -> tuple[SpecimenRun, SpecimenRun]:
    long_spec = make_spec(SpecimenRole.ELASTIC, l0=long_l0).danger_ok
    short_spec = make_spec(SpecimenRole.PLASTIC).danger_ok
    el = SpecimenRun(
        spec=long_spec, inputs=tuple(_elastic_points(long_spec.l0_m, masses)), window=(0, 5)
    )
    pl = SpecimenRun(spec=short_spec, inputs=tuple(_plastic_points(short_spec.l0_m)), window=(0, 5))
    return el, pl


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.steps
# frob:tests python/sadi/labs/lctt/lab.py::lctt_steps
def test_steps_and_phase_binding() -> None:
    steps = LcttLab().steps()
    assert [s.id for s in steps] == [
        "setup", "calibrate", "tare", "elastic", "plastic", "results", "export"
    ]  # fmt: skip
    by_id = {str(s.id): s.phase for s in steps}
    assert by_id["calibrate"] is Phase.CALIBRATION
    assert by_id["elastic"] is Phase.ELASTIC
    assert by_id["plastic"] is Phase.PLASTIC
    assert by_id["tare"] is Phase.TARE
    assert by_id["results"] is Phase.RESULTS
    assert by_id["export"] is Phase.EXPORT
    assert "weights" not in by_id


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab
def test_registered_via_plugin_mechanism() -> None:
    labs = LabRegistry.from_plugins(PluginRegistry.discover([builtin_source()]))
    got = labs.get(LabId("lctt"))
    assert isinstance(got, Ok)
    assert len(got.danger_ok.steps()) == 7


# frob:tests python/sadi/labs/lctt/specimens.py::SpecimenSpec
# frob:tests python/sadi/labs/lctt/specimens.py::SpecimenSpec.kind
# frob:tests python/sadi/labs/lctt/specimens.py::SpecimenSpec.l0_m
# frob:tests python/sadi/labs/lctt/specimens.py::SpecimenSpec.loading_options
# frob:tests python/sadi/labs/lctt/specimens.py::with_l0
def test_default_and_editable_lengths() -> None:
    long_spec = make_spec(SpecimenRole.ELASTIC).danger_ok
    short_spec = make_spec(SpecimenRole.PLASTIC).danger_ok
    assert long_spec.l0_m == 0.5
    assert short_spec.l0_m == 0.08313
    edited = with_l0(long_spec, 0.62)
    assert isinstance(edited, Ok) and edited.danger_ok.l0_m == 0.62
    assert edited.danger_ok.loading_options().gauge_length == 0.62


# frob:tests python/sadi/labs/lctt/specimens.py::make_spec
@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan"), float("inf")])
def test_bad_length_rejected(bad: float) -> None:
    out = make_spec(SpecimenRole.ELASTIC, l0=bad)
    assert isinstance(out, Err) and out.danger_err == SpecimenError.BadLength


# frob:tests python/sadi/labs/lctt/lab.py::combine_runs
# frob:tests python/sadi/labs/lctt/lab.py::TwoSpecimenResults.get
def test_results_combine_with_sources() -> None:
    el, pl = _runs()
    out = combine_runs(el, pl, _shared())
    assert isinstance(out, Ok), out
    res = out.danger_ok
    e = res.get("E")
    y = res.get("yield_stress")
    assert e is not None and y is not None
    assert e.role is SpecimenRole.ELASTIC and e.l0_m == 0.5
    assert y.role is SpecimenRole.PLASTIC and y.l0_m == 0.08313
    assert e.source != y.source
    assert e.result.value == pytest.approx(E_TRUE, rel=1e-3)
    assert y.result.value > 0
    assert not res.pending


# frob:tests python/sadi/labs/lctt/lab.py::combine_runs
def test_edited_long_length_changes_source_and_keeps_e() -> None:
    el, pl = _runs(long_l0=0.62)
    res = combine_runs(el, pl, _shared()).danger_ok
    e = res.get("E")
    assert e is not None and e.l0_m == 0.62
    assert e.result.value == pytest.approx(E_TRUE, rel=1e-3)


# frob:tests python/sadi/labs/lctt/lab.py::combine_runs
def test_swapped_weights_need_no_reentry() -> None:
    """Calibration heights differ from experiment masses; a different mass set reuses the same
    shared calibration/tare inputs and the runs still give the same E."""
    shared = _shared(heights=(0.0, 0.02, 0.04, 0.06, 0.08))
    a = combine_runs(*_runs(masses=(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)), shared).danger_ok
    b = combine_runs(*_runs(masses=(0.5, 1.5, 2.5, 3.5, 4.5, 5.5)), shared).danger_ok
    ea, eb = a.get("E"), b.get("E")
    assert ea is not None and eb is not None
    assert ea.result.value == pytest.approx(eb.result.value, rel=1e-3)


# frob:tests python/sadi/labs/lctt/lab.py::combine_runs
def test_wrong_roles_rejected() -> None:
    el, pl = _runs()
    out = combine_runs(pl, el, _shared())
    assert isinstance(out, Err) and out.danger_err == LabError.WrongRole


# frob:tests python/sadi/labs/lctt/lab.py::combine_runs
def test_missing_inputs_leave_results_pending() -> None:
    el, pl = _runs()
    out = combine_runs(el, pl, [])
    assert isinstance(out, Ok)
    assert set(out.danger_ok.pending) == {"E", "r2", "yield_stress"}


# frob:tests python/sadi/labs/lctt/lab.py::events_from_inputs
def test_events_from_inputs_ids_per_run() -> None:
    evs = events_from_inputs(_elastic_points(0.5, (1.0, 2.0)), "elastic").danger_ok
    ids = [getattr(e, "point_id", None) for e in evs]
    assert ids == [None, "elastic-0", "elastic-1"]


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.recompute
def test_core_recompute_real_values() -> None:
    from sadi.core.models import CapturedPoint, SettleStatus, TimeWindow
    from sadi.labs.lctt.lab import LoadingContext

    def pt(i: int, v: float | None, kg: float | None) -> CapturedPoint:
        return CapturedPoint(
            index=i,
            window=TimeWindow(start=0.0, end=1.0),
            t_since_load=1.0,
            drift_rate=0.0,
            status=SettleStatus.SETTLED,
            volts=v,
            load_kg=kg,
        )

    assert isinstance(LcttLab().recompute(()), Err)
    assert isinstance(LcttLab().recompute((pt(0, None, None),)), Err)
    pts = (pt(0, None, 1.0), pt(1, 2.0, 1.0))
    res = LcttLab().recompute(pts).danger_ok
    assert set(res.values) == {"stress"}
    assert res.values["stress"].value > 0
    ctx = LoadingContext(slope_m_per_v=0.01, tare_v=1.0, l0_m=0.5)
    full = LcttLab(ctx).recompute(pts).danger_ok
    assert set(full.values) == {"stress", "strain", "secant_modulus"}
    assert full.values["strain"].value == pytest.approx(0.01 * 1.0 / 0.5)


# frob:tests python/sadi/labs/lctt/specimens.py::SpecimenSpec.name
def test_spec_name_prefers_label() -> None:
    assert SpecimenSpec(role=SpecimenRole.PLASTIC, label="wire B").name == "wire B"
