"""Tests for the command-line weight planner and its shared parsers."""

# creates:python/tests/design/test_cli.py
# frob:ticket 01M72ZGDCC7C75SMXSJRH6VBAE

from __future__ import annotations

import pytest
from typani import Err, Ok

from sadi.design.cli import build_request, main, parse_captured, parse_weights

_ARGS = ["--weights", "0.1,0.1,0.2,0.5", "--length", "0.083", "--cal-slope", "12.0"]


def test_parse_weights_keeps_duplicates_distinct():
    res = parse_weights("0.1, 0.1,0.2", 1e-4)
    assert isinstance(res, Ok)
    assert [w.weight_id for w in res.value] == ["w1", "w2", "w3"]
    assert [w.mass_kg for w in res.value] == [0.1, 0.1, 0.2]


def test_parse_weights_rejects_garbage():
    assert isinstance(parse_weights("0.1,abc", 0.0), Err)


def test_parse_captured_roundtrip_and_errors():
    res = parse_captured("0.1:0.5,0.3:1.4")
    assert isinstance(res, Ok) and [(c.mass_kg, c.volts) for c in res.value] == [(0.1, 0.5), (0.3, 1.4)]
    assert isinstance(parse_captured("0.1"), Err)
    assert parse_captured("") == Ok([])


def test_build_request_reports_invalid_geometry():
    res = build_request(
        weights="0.1", u_mass=0.0, diameter=-1.0, u_diameter=0.0, length=0.1, u_length=0.0,
        cal_slope=1.0, cal_offset=0.0, saturation=None, captured="",
    )
    assert isinstance(res, Err)


def test_main_prints_table(capsys):
    assert main(_ARGS) == 0
    out = capsys.readouterr().out
    assert "phase=" in out and "pred_V" in out


def test_main_bad_weights_nonzero(capsys):
    assert main(["--weights", "x", "--length", "0.083", "--cal-slope", "12"]) == 1
    assert "No plan" in capsys.readouterr().out


def test_main_requires_cal_slope():
    with pytest.raises(SystemExit):
        main(["--weights", "0.1", "--length", "0.083"])
