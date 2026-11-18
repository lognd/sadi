"""Mid-run PARTIAL lctt CSV and standalone calibration CSV (any wizard step, no data loss)."""

# frob:ticket 01M72ZDQGAN0VQRKHM489H28J1
# creates:python/tests/labs/lctt/test_partial_export.py

from __future__ import annotations

from sadi.core.lab import AnalysisResult
from sadi.core.models import RunState
from sadi.labs.lctt.export_csv import (
    ExportCsvError,
    build_calibration_csv,
    build_document,
    read_document,
    render_document,
)
from sadi.labs.lctt.lab import CALIBRATION_CSV_FORMAT, PARTIAL_CSV_FORMAT
from sadi.labs.lctt.live import CalPoint, TareBlock
from tests.labs.lctt.test_export_csv import NOW, _events

_CAL = [CalPoint(volts=v, height=0.08 + 0.002 * v) for v in range(1, 6)]


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_partial_with_calibration_only_has_fit_and_label() -> None:
    """Calibration alone gives a PARTIAL document with cal points, fit, n and r2 and no rows."""
    doc = build_document(_CAL, date=NOW, partial=True)
    assert doc.is_ok
    d = doc.danger_ok
    assert d.get("Status") == "PARTIAL"
    assert d.get("Cal n") == "5"
    assert d.get_float("Cal r2") > 0.99
    assert d.get("Cal point 5 volts (V)") == "5"
    assert not d.rows
    assert read_document(render_document(d)).is_ok


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_partial_with_tare_but_no_points_still_works() -> None:
    """Calibration plus tare (no specimen or points) is still a valid PARTIAL document."""
    doc = build_document([*_CAL, TareBlock(mean=0.5, sd=0.001, n=20)], date=NOW, partial=True)
    assert doc.is_ok
    assert doc.danger_ok.get("Status") == "PARTIAL"


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_partial_with_points_keeps_rows_and_full_stays_unlabelled() -> None:
    """A run with points is labelled only when partial; complete exports are unchanged."""
    part = build_document(_events(8), date=NOW, partial=True).danger_ok
    full = build_document(_events(8), date=NOW).danger_ok
    assert part.get("Status") == "PARTIAL"
    assert len(part.rows) == 8
    assert full.get("Status") is None


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_complete_export_still_refuses_without_points() -> None:
    """Non-partial export keeps refusing an unready session; partial refuses only with no cal."""
    full = build_document(_CAL, date=NOW)
    assert full.is_err
    assert full.danger_err == ExportCsvError.NotReady
    assert build_document([], date=NOW, partial=True).is_err


# frob:tests python/sadi/labs/lctt/export_csv.py::build_calibration_csv
def test_calibration_csv_lists_points_and_fit() -> None:
    """The standalone calibration CSV carries slope/intercept/se/t95/U95/r2/n and each point."""
    out = build_calibration_csv(_CAL, date=NOW)
    assert out.is_ok
    text = out.danger_ok.decode("utf-8")
    for key in ("Cal slope (m/V)", "Cal se slope", "Cal t95", "Cal U95 slope", "Cal r2", "Cal n"):
        assert key in text
    assert "point,volts (V),height (m)" in text
    assert text.count("\r\n") > 12
    assert build_calibration_csv([], date=NOW).is_err


# frob:tests python/sadi/labs/lctt/lab.py::_write_csv_partial
# frob:tests python/sadi/labs/lctt/lab.py::_write_calibration_csv
def test_lab_writers_serve_from_run_events() -> None:
    """Both mid-run formats render from raw events on the RunState without finishing a phase."""
    run = RunState(session_id="s", events=tuple(_CAL))
    part = PARTIAL_CSV_FORMAT.writer(run, AnalysisResult(values={}))
    cal = CALIBRATION_CSV_FORMAT.writer(run, AnalysisResult(values={}))
    assert part.is_ok
    assert b"PARTIAL" in part.danger_ok
    assert cal.is_ok
    empty = RunState(session_id="s", events=())
    assert PARTIAL_CSV_FORMAT.writer(empty, AnalysisResult(values={})).is_err
