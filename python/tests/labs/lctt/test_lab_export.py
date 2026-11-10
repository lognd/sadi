"""The lctt lab declares the lctt-csv export format and renders it from raw session events."""

# frob:ticket 01M6WVADB5YKXAVC43CQNBQVJW

from __future__ import annotations

import json

from sadi.core.lab import AnalysisResult
from sadi.core.models import RunState
from sadi.labs.lctt.export_csv import read_document
from sadi.labs.lctt.figure_data import figure_data
from sadi.labs.lctt.lab import CSV_FORMAT, FIGURE_FORMAT, LcttLab
from tests.labs.lctt.test_export_csv import _events


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab
def test_lab_declares_lctt_csv() -> None:
    """The lab lists exactly the CSV format with a text/csv media type."""
    fmts = LcttLab().export_formats
    assert [f.id for f in fmts] == (
        ["lctt-csv", "lctt-csv-partial", "lctt-calibration-csv", "lctt-figure-json"]
    )
    assert fmts[0].media_type == "text/csv"
    assert fmts[-1].media_type == "application/json"


# frob:ticket 01M6WYHZA2BAKB92CQENP7G7SD
# frob:tests python/sadi/labs/lctt/lab.py::_write_csv
def test_writer_renders_full_header_from_run_events() -> None:
    """Events on the RunState produce a CSV the reader parses back with every point."""
    run = RunState(session_id="s", events=tuple(_events(8)))
    out = CSV_FORMAT.writer(run, AnalysisResult(values={}))
    assert out.is_ok
    doc = read_document(out.danger_ok)
    assert doc.is_ok
    assert len(doc.danger_ok.rows) == 8


# frob:tests python/sadi/labs/lctt/lab.py::_write_csv
def test_writer_refuses_without_events() -> None:
    """A session with no recorded inputs is a compute error, not an empty file."""
    out = CSV_FORMAT.writer(RunState(session_id="s"), AnalysisResult(values={}))
    assert out.is_err


# frob:tests python/sadi/labs/lctt/lab.py::_write_figure_json
def test_figure_json_has_both_series() -> None:
    """Events produce JSON with a calibration fit and one stress-strain entry per point."""
    run = RunState(session_id="s", events=tuple(_events(8)))
    out = FIGURE_FORMAT.writer(run, AnalysisResult(values={}))
    assert out.is_ok
    doc = json.loads(out.danger_ok)
    assert doc["calibration"]["fit"] is not None
    ss = doc["stress_strain"]
    assert len(ss["strain"]) == len(ss["stress_mpa"]) == len(ss["excluded"]) == 8


# frob:tests python/sadi/labs/lctt/lab.py::_write_figure_json
def test_figure_json_refuses_without_events() -> None:
    """A session with no recorded inputs is a compute error, not an empty document."""
    out = FIGURE_FORMAT.writer(RunState(session_id="s"), AnalysisResult(values={}))
    assert out.is_err


# frob:tests python/sadi/labs/lctt/figure_data.py::figure_data
# frob:tests python/sadi/labs/lctt/figure_data.py::calibration_data
# frob:tests python/sadi/labs/lctt/figure_data.py::stress_strain_data
def test_figure_data_series_lengths_agree() -> None:
    """Calibration and stress-strain series are equal-length within each figure."""
    out = figure_data(_events(8))
    assert out.is_ok
    cal = out.danger_ok.calibration
    assert len(cal.volts) == len(cal.height_m)
    assert figure_data([]).is_err
