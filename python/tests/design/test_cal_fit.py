"""Tests for deriving the planner calibration from height/volts points."""

# creates:python/tests/design/test_cal_fit.py
# frob:ticket 01M7301MDWNXK9Z0D8TBDBNP4G

from __future__ import annotations

import pytest
from typani import Err, Ok

from sadi.design.cal_fit import parse_cal_points, resolve_calibration
from sadi.design.cli import main
from sadi.design.gui import plan_from_form

PTS = "0.001:0.1,0.002:0.21,0.003:0.29,0.004:0.41"
_WIRE = ["--weights", "0.1,0.2,0.5", "--length", "0.083"]
FORM = {
    "weights": "0.1,0.2,0.5", "u_mass": "0", "diameter": "0.0002019", "length": "0.08313",
    "cal_points": PTS, "cal_slope": "", "cal_offset": "0",
}


# frob:tests python/sadi/design/cal_fit.py::parse_cal_points
def test_parse_cal_points():
    res = parse_cal_points("0.1:1,0.2:2")
    assert res == Ok([(0.1, 1.0, None), (0.2, 2.0, None)])
    assert isinstance(parse_cal_points("0.1"), Err)
    assert isinstance(parse_cal_points("a:b"), Err)


# frob:tests python/sadi/design/cal_fit.py::resolve_calibration
def test_fit_recovers_slope_with_uncertainty():
    res = resolve_calibration("0:0,1:100,2:200,3:300", None)
    assert isinstance(res, Ok)
    c = res.value
    assert c.source == "fit" and c.n == 4
    assert c.slope_v_per_m == pytest.approx(100.0) and c.offset_v == pytest.approx(0.0, abs=1e-9)
    assert c.r2 == pytest.approx(1.0) and "fitted" in c.summary()


def test_fit_reports_nonzero_se_on_noisy_data():
    res = resolve_calibration(PTS, None)
    assert isinstance(res, Ok) and res.value.se_slope > 0 and res.value.se_offset > 0


@pytest.mark.parametrize("pts", ["0.1:1,0.1:2,0.1:3", "0.1:1", "0.1:1,0.2:2", ""])
def test_degenerate_points_are_clear_errors(pts):
    res = resolve_calibration(pts, None)
    assert isinstance(res, Err) and res.error


# frob:tests python/sadi/design/cal_fit.py::Calibration.summary
def test_override_is_labelled_and_exclusive():
    res = resolve_calibration("", 12.0, 0.5)
    assert isinstance(res, Ok) and res.value.source == "override" and "OVERRIDE" in res.value.summary()
    assert isinstance(resolve_calibration(PTS, 12.0), Err)


# frob:tests python/sadi/design/cli.py::main
def test_cli_fit_prints_calibration(capsys):
    assert main([*_WIRE, "--cal-points", PTS]) == 0
    assert "fitted slope" in capsys.readouterr().out


def test_cli_override_labelled(capsys):
    assert main([*_WIRE, "--cal-slope", "12"]) == 0
    assert "OVERRIDE" in capsys.readouterr().out


def test_cli_single_height_errors(capsys):
    assert main([*_WIRE, "--cal-points", "0.1:1,0.1:2,0.1:3"]) == 1
    assert "distinct heights" in capsys.readouterr().out


# frob:tests python/sadi/design/gui.py::plan_from_form
def test_gui_fit_and_uncertainty_propagates():
    out = plan_from_form(FORM)
    assert out["ok"] and out["cal"]["source"] == "fit" and out["cal"]["se_slope"] > 0
    assert all(h["u_volts"] > 0 for h in out["hangs"])
    ovr = plan_from_form({**FORM, "cal_points": "", "cal_slope": "100"})
    assert ovr["ok"] and ovr["cal"]["source"] == "override"
    assert all(h["u_volts"] == 0 for h in ovr["hangs"])


def test_gui_no_calibration_is_error():
    out = plan_from_form({**FORM, "cal_points": ""})
    assert not out["ok"] and "calibration" in out["error"]


# frob:tests python/sadi/design/cal_fit.py::parse_cal_points
def test_height_uncertainty_parsed_and_weighted():
    assert parse_cal_points("0.1:1:0.001,0.2:2") == Ok([(0.1, 1.0, 0.001), (0.2, 2.0, None)])
    plain = resolve_calibration(PTS, None)
    wtd = resolve_calibration("0.001:0.1:0.0001,0.002:0.21:0.0001,0.003:0.29:0.0002,0.004:0.41:0.0001", None)
    assert isinstance(plain, Ok) and isinstance(wtd, Ok)
    assert wtd.value.se_slope != plain.value.se_slope and wtd.value.se_slope > 0
    mixed = resolve_calibration("0.001:0.1:0.0001,0.002:0.21,0.003:0.29,0.004:0.41", None)
    assert isinstance(mixed, Ok) and mixed.value.se_slope == pytest.approx(plain.value.se_slope)
