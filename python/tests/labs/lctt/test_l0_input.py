"""Operator-typed L0 and hanger-mass uncertainty flow into strain, E and the CSV."""

# frob:ticket 01M72Y13R6WWH4G55AMHQEPVZH

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from typani import Err, Ok

from sadi.core.point_inputs import SpecimenInputs, check_ranges, parse_inputs
from sadi.labs.lctt.export_csv import build_document
from sadi.labs.lctt.lab import context_from_inputs
from sadi.labs.lctt.live import CalPoint, LiveEvent, LoadPoint, SpecimenSetup, TareBlock

NOW = datetime(2026, 11, 10, tzinfo=UTC)


def _events(l0: float | None, u_l0: float = 0.0, u_hang: float = 1e-3) -> list[LiveEvent]:
    """Synthetic session with an optional L0 override on the specimen step."""
    ev: list[LiveEvent] = [CalPoint(volts=v, height=0.08 + 0.002 * v) for v in range(1, 9)]
    ev.append(TareBlock(mean=0.5, sd=0.001, n=20))
    ev.append(
        SpecimenSetup(diameter=0.003, u_diameter=1e-5, hanger_kg=0.5, u_hanger_kg=u_hang,
                      l0_m=l0, u_l0_m=u_l0)
    )  # fmt: skip
    for i in range(6):
        ev.append(
            LoadPoint(point_id=f"p{i}", volts=0.5 + 0.01 * (i + 1), mass_kg=0.2 * (i + 1),
                      u_mass_kg=1e-4, u_volts=1e-4, volts_sd=2e-4)
        )  # fmt: skip
    return ev


def _rows(l0: float | None, u_l0: float = 0.0, u_hang: float = 1e-3):  # noqa: ANN202
    built = build_document(_events(l0, u_l0, u_hang), date=NOW, operator="o", description="d")
    assert isinstance(built, Ok), built
    return built.danger_ok.rows


# frob:tests python/sadi/core/point_inputs.py::parse_inputs
def test_parse_accepts_l0_and_hanger_uncertainty() -> None:
    got = parse_inputs(
        "specimen", {"diameter": 0.003, "l0_m": 0.25, "u_l0_m": 1e-4, "u_hanger_kg": 2e-3}
    ).danger_ok
    assert isinstance(got, SpecimenInputs)
    assert (got.l0_m, got.u_l0_m, got.u_hanger_kg) == (0.25, 1e-4, 2e-3)


# frob:tests python/sadi/core/point_inputs.py::parse_inputs
def test_blank_l0_stays_default() -> None:
    got = parse_inputs("specimen", {"diameter": 0.003}).danger_ok
    assert isinstance(got, SpecimenInputs)
    assert got.l0_m is None
    assert got.u_l0_m == 0.0


# frob:tests python/sadi/core/point_inputs.py::check_ranges
def test_l0_range_rejects_millimetre_slip_and_negative_u() -> None:
    bad = SpecimenInputs(diameter=0.003, l0_m=83.13)
    assert isinstance(check_ranges(bad), Err)
    assert isinstance(check_ranges(SpecimenInputs(diameter=0.003, u_l0_m=-1.0)), Err)
    assert isinstance(check_ranges(SpecimenInputs(diameter=0.003, l0_m=0.5, u_l0_m=1e-4)), Ok)


# frob:tests python/sadi/labs/lctt/lab.py::context_from_inputs
def test_context_uses_typed_l0_and_hanger_uncertainty() -> None:
    ctx = context_from_inputs(
        [SpecimenInputs(diameter=0.003, hanger_kg=0.5, u_hanger_kg=2e-3, l0_m=0.3, u_l0_m=1e-4)]
    )
    assert (ctx.l0_override_m, ctx.u_l0_m, ctx.u_hanger_kg) == (0.3, 1e-4, 2e-3)


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_csv_uses_typed_l0_for_strain_and_reports_it() -> None:
    default, typed = _rows(None), _rows(0.25, 5e-4)
    assert default[0].l0_m == 0.08313
    assert typed[0].l0_m == 0.25
    assert typed[0].u_l0_m == 5e-4
    assert typed[1].strain == pytest.approx(default[1].strain * 0.08313 / 0.25, rel=1e-9)
    assert typed[1].u_strain > 0.0


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_hanger_uncertainty_widens_load_uncertainty() -> None:
    lo, hi = _rows(None, u_hang=0.0), _rows(None, u_hang=0.05)
    assert hi[0].u_hanger_n > lo[0].u_hanger_n == 0.0
    assert hi[2].u_load_n > lo[2].u_load_n
