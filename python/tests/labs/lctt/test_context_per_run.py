"""context_from_inputs analyses each point under its own run's specimen, tare and L0."""

# frob:ticket 01M71V64GMPG77XEX6MKYMTZJH

from __future__ import annotations

from datetime import UTC, datetime

from typani import Ok

from sadi.core.point_inputs import LoadInputs, SpecimenInputs, TareInputs
from sadi.labs.lctt.export_csv import build_document, to_live_events
from sadi.labs.lctt.lab import context_from_inputs
from sadi.labs.lctt.live import CalPoint, LoadPoint, SpecimenSetup, TareBlock
from sadi.labs.lctt.loading import LONG_L0_M, SHORT_L0_M


def _two_runs() -> list:  # noqa: ANN202
    """Elastic run (d=3mm, tare 0.5) then plastic run (d=4mm, tare 0.7)."""
    return [
        TareInputs(mean=0.5, sd=0.001, n=20),
        SpecimenInputs(diameter=0.003, hanger_kg=0.5),
        LoadInputs(phase="elastic", volts=0.6, mass_kg=1.0),
        TareInputs(mean=0.7, sd=0.001, n=20),
        SpecimenInputs(diameter=0.004, hanger_kg=0.25, l0_m=0.07),
        LoadInputs(phase="plastic", volts=0.9, mass_kg=2.0),
    ]


# frob:tests python/sadi/labs/lctt/lab.py::context_from_inputs
def test_last_point_uses_its_own_run_setup() -> None:
    """The plastic point gets the plastic specimen, tare and L0, not a mix."""
    ctx = context_from_inputs(_two_runs())
    assert ctx.diameter_m == 0.004
    assert ctx.hanger_kg == 0.25
    assert ctx.tare_v == 0.7
    assert ctx.l0_m == 0.07


# frob:tests python/sadi/labs/lctt/lab.py::context_from_inputs
def test_elastic_context_ignores_later_plastic_run() -> None:
    """Truncated at the elastic point, the context is the elastic run's own."""
    ctx = context_from_inputs(_two_runs()[:3])
    assert (ctx.diameter_m, ctx.tare_v, ctx.l0_m) == (0.003, 0.5, LONG_L0_M)


# frob:tests python/sadi/labs/lctt/lab.py::context_from_inputs
def test_tare_pools_only_within_run() -> None:
    """A tare after a load starts a fresh group; legacy order pools all blocks."""
    legacy = [
        TareInputs(mean=0.5, sd=0.0, n=10),
        TareInputs(mean=0.7, sd=0.0, n=10),
        SpecimenInputs(diameter=0.003),
        LoadInputs(phase="plastic", volts=0.6, mass_kg=1.0),
    ]
    assert abs((context_from_inputs(legacy).tare_v or 0.0) - 0.6) < 1e-9
    assert context_from_inputs(_two_runs()).tare_v == 0.7
    assert SHORT_L0_M != LONG_L0_M


# frob:tests python/sadi/labs/lctt/export_csv.py::to_live_events
def test_reload_keeps_hanger_unc_and_l0() -> None:
    """A CSV round-trip keeps u_hanger_kg, the L0 override and its uncertainty."""
    ev: list = [CalPoint(volts=v, height=0.08 + 0.002 * v) for v in range(1, 9)]
    ev.append(TareBlock(mean=0.5, sd=0.001, n=20))
    ev.append(SpecimenSetup(diameter=0.003, u_diameter=1e-5, hanger_kg=0.5, u_hanger_kg=1e-3,
                            l0_m=0.4, u_l0_m=2e-3))  # fmt: skip
    for i in range(6):
        ev.append(LoadPoint(point_id=f"p{i}", volts=0.5 + 0.01 * (i + 1),
                            mass_kg=0.2 * (i + 1), phase="elastic"))  # fmt: skip
    built = build_document(ev, date=datetime(2026, 11, 10, tzinfo=UTC), operator="o",
                           description="d")  # fmt: skip
    assert isinstance(built, Ok)
    spec = next(e for e in to_live_events(built.danger_ok) if isinstance(e, SpecimenSetup))
    assert spec.u_hanger_kg == 1e-3
    assert spec.l0_m == 0.4
    assert spec.u_l0_m == 2e-3
