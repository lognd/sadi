"""CSV export must agree with the Results path: per-phase L0, E from elastic, yield from plastic."""

# frob:ticket 01M729642YCP4MRYBWBNQBYW7A
from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from sadi.core.point_inputs import LoadInputs, PointInputs
from sadi.labs.lctt.export_csv import build_document, read_document, render_document, to_live_events
from sadi.labs.lctt.lab import LcttLab, events_from_inputs
from sadi.labs.lctt.live import LiveEvent
from tests.labs.lctt.test_lab import _captured, _phased, _plastic_points, _shared

NOW = datetime(2026, 11, 10, tzinfo=UTC)
LONG_L0, SHORT_L0 = 0.5, 0.08313


def _inputs() -> list[PointInputs]:
    """Calibration, tare, specimen, then an elastic (L0 0.5) and plastic (L0 0.08313) run."""
    return [
        *_shared(),
        *_phased(_plastic_points(LONG_L0), "elastic"),
        *_phased(_plastic_points(SHORT_L0), "plastic"),
    ]


def _events(inputs: list[PointInputs]) -> list[LiveEvent]:
    """Live events for both runs in log order, phase-tagged like the server's replay."""
    shared = [i for i in inputs if not isinstance(i, LoadInputs)]
    out = events_from_inputs(shared, "s").danger_ok
    for role in ("elastic", "plastic"):
        loads = [i for i in inputs if isinstance(i, LoadInputs) and i.phase == role]
        out += [e for e in events_from_inputs(loads, role).danger_ok if e.kind == "point"]
    return out


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_csv_values_equal_results() -> None:
    """CSV E, r2, yield and tare match the Results the lab reports."""
    inputs = _inputs()
    res = LcttLab().analyze(_captured(inputs), inputs).danger_ok.values
    doc = build_document(_events(inputs), date=NOW)
    assert doc.is_ok
    d = doc.danger_ok
    assert d.get_float("E (Pa)") == pytest.approx(res["E"].value, rel=1e-9)
    assert d.get_float("E r2") == pytest.approx(res["r2"].value, rel=1e-9)
    assert d.get_float("Yield stress (Pa)") == pytest.approx(res["yield_stress"].value, rel=1e-9)
    assert d.get_float("Tare u (V)") == pytest.approx(res["tare"].standard_uncertainty, rel=1e-9)
    assert d.get_float("Tare mean (V)") == pytest.approx(res["tare"].value, rel=1e-9)
    want = res["tare"].standard_uncertainty
    assert all(math.isclose(r.u_tare_v, want, rel_tol=1e-9) for r in d.rows)


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_rows_carry_phase_and_own_gauge_length() -> None:
    """Each row keeps its phase and that phase's gauge length."""
    d = build_document(_events(_inputs()), date=NOW).danger_ok
    assert {r.phase for r in d.rows} == {"elastic", "plastic"}
    for r in d.rows:
        assert r.l0_m == (LONG_L0 if r.phase == "elastic" else SHORT_L0)
    assert d.get_float("Elastic L0 (m)") == LONG_L0
    assert d.get_float("Plastic L0 (m)") == SHORT_L0
    assert d.get("Schema") == "5"
    assert not any(r.is_yield for r in d.rows if r.phase == "elastic")


# frob:tests python/sadi/labs/lctt/export_csv.py::to_live_events
def test_phase_survives_render_read_roundtrip() -> None:
    """Phase and E survive render, read and rebuild."""
    d = build_document(_events(_inputs()), date=NOW).danger_ok
    back = read_document(render_document(d)).danger_ok
    assert [r.phase for r in back.rows] == [r.phase for r in d.rows]
    again = build_document(to_live_events(back), date=NOW).danger_ok
    assert math.isclose(again.get_float("E (Pa)"), d.get_float("E (Pa)"), rel_tol=1e-6)


# frob:ticket 01M72D3CTDED2MGDY721RSM8M4
# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_row_uncertainty_model_is_consistent() -> None:
    """u_strain agrees with u_displacement_m / l0_m (same Sx/sqrt(N) tare), not 2 Sx."""
    d = build_document(_events(_inputs()), date=NOW).danger_ok
    assert "Sx/sqrt(N)" in d.get("Row uncertainty model")
    for r in d.rows:
        if r.strain == 0:
            continue
        # area/L0 contribute nothing to strain, so the two views must be the same number
        assert r.u_strain == pytest.approx(r.u_displacement_m / r.l0_m, rel=0.35)
