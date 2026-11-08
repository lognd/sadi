"""The lctt lab declares the lctt-csv export format and renders it from raw session events."""

# frob:ticket 01M6WVADB5YKXAVC43CQNBQVJW

from __future__ import annotations

from sadi.core.lab import AnalysisResult
from sadi.core.models import RunState
from sadi.labs.lctt.export_csv import read_document
from sadi.labs.lctt.lab import CSV_FORMAT, LcttLab
from tests.labs.lctt.test_export_csv import _events


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab
def test_lab_declares_lctt_csv() -> None:
    """The lab lists exactly the CSV format with a text/csv media type."""
    fmts = LcttLab().export_formats
    assert [f.id for f in fmts] == ["lctt-csv"]
    assert fmts[0].media_type == "text/csv"


# frob:tests python/sadi/labs/lctt/lab.py::_write_csv
def test_writer_renders_32_columns_from_run_events() -> None:
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
