"""Unit-slip ranges (mm as m, g as kg), the calibration quality gate and the assumed diameter."""

# frob:ticket 01M7230XMB52H0AA8ETNQ8RBPX

from __future__ import annotations

from sadi.core.models import CapturedPoint, SettleStatus, TimeWindow
from sadi.core.point_inputs import CalibrationInputs, LoadInputs, check_ranges
from sadi.labs.lctt.lab import LcttLab, calibration_gate


def _line(n: int = 5) -> list[dict[str, float]]:
    return [{"volts": 0.1 * i, "height": 0.004 * i} for i in range(1, n + 1)]


# frob:tests python/sadi/core/point_inputs.py::check_ranges
def test_height_one_is_rejected_with_mm_hint() -> None:
    """A 1 mm block typed as 1 is rejected and the message offers 0.001 m."""
    bad = check_ranges(CalibrationInputs(volts=0.1, height=1.0))
    assert bad.is_err
    assert "millimetres" in bad.danger_err and "0.001" in bad.danger_err
    assert check_ranges(CalibrationInputs(volts=0.1, height=0.001)).is_ok


# frob:tests python/sadi/core/point_inputs.py::check_ranges
def test_mass_in_grams_is_rejected_with_gram_hint() -> None:
    """500 typed as kg is rejected with a grams hint; 0.5 kg passes."""
    bad = check_ranges(LoadInputs(phase="elastic", volts=0.1, mass_kg=500.0))
    assert bad.is_err and "grams" in bad.danger_err
    assert check_ranges(LoadInputs(phase="elastic", volts=0.1, mass_kg=0.5)).is_ok


# frob:tests python/sadi/labs/lctt/lab.py::calibration_gate
def test_gate_blocks_mm_slip_and_names_worst_point() -> None:
    """Heights 1, .002, .003, .004 give a poor fit; the message names the worst point."""
    pts = [
        {"volts": 0.1 * (i + 1), "height": h} for i, h in enumerate([1.0, 0.002, 0.003, 0.004])
    ]
    why = calibration_gate(pts)
    assert why is not None and "point 1" in why


# frob:tests python/sadi/labs/lctt/lab.py::calibration_gate
def test_gate_blocks_negative_slope_and_outlier_and_passes_good() -> None:
    """Falling slope and a single outlier are blocked; a clean line passes."""
    neg = [{"volts": p["volts"], "height": -p["height"]} for p in _line()]
    assert "slope" in (calibration_gate(neg) or "")
    out = _line(8)
    out[3] = {"volts": out[3]["volts"], "height": out[3]["height"] + 0.004}
    assert calibration_gate(out) is not None
    assert calibration_gate(_line()) is None


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.analyze
def test_missing_diameter_adds_note() -> None:
    """Without a specimen point the result carries a 'diameter assumed' note."""
    pt = CapturedPoint(
        index=0,
        window=TimeWindow(start=0.0, end=1.0),
        t_since_load=1.0,
        drift_rate=0.0,
        status=SettleStatus.SETTLED,
        volts=0.1,
        load_kg=0.1,
    )
    res = LcttLab().analyze((pt,), [])
    assert res.is_ok
    assert any("diameter assumed" in n for n in res.danger_ok.notes)


# frob:tests python/sadi/labs/lctt/lab.py::diameter_assumed_note
def test_diameter_assumed_note_text() -> None:
    """The note states the assumed size and what to do."""
    from sadi.labs.lctt.lab import diameter_assumed_note  # noqa: PLC0415

    assert "diameter assumed 6 mm" in diameter_assumed_note()
