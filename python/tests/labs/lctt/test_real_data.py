"""Local lab data validation (skipped when the data is absent): calibration fit vs the VI and detect_slip on short-run."""

# frob:ticket 01M6WE7E19D77NKF83TE5AM8Q6
# frob:ticket 01M6WEWKHPZ6NW5ZV7XDB1VK7J

from __future__ import annotations

import csv
from pathlib import Path

import pytest
from typani import Ok

from sadi.labs.lctt.calibration import fit_calibration
from sadi.labs.lctt.slip import SlipConfig, SlipReport, detect_slip
from sadi.logging_setup import get_logger

_log = get_logger(__name__)
FIX = Path(__file__).resolve().parents[2] / "fixtures" / "real_fp"
REL = 1e-6

needs_data = pytest.mark.skipif(
    not FIX.is_dir(), reason="local lab data (real_fp fixtures) not present; kept out of git"
)

# lvdt_calibration.txt as printed by the VI (6 significant digits)
VI_TXT = {
    "slope": 2.114583e-3,
    "intercept": 2.472866e-2,
    "se_slope": 6.734580e-6,
    "se_intercept": 1.970728e-5,
    "r2": 9.998986e-1,
    "t95": 2.228139,
    "n": 12,
}
# Same VI run at full precision, from the the local short-run file header block ("Cal ..." rows)
VI_CSV = {
    "se_slope": 6.734591237e-6,
    "se_intercept": 1.97073156e-5,
    "r2": 0.9998985788,
    "t95": 2.228138852,
}


def _points() -> tuple[list[float], list[float]]:
    """Read the 12 calibration points from the trimmed fixture (header row skipped)."""
    rows = (FIX / "lvdt_calibration_points.tsv").read_text(encoding="ascii").splitlines()[1:]
    pairs = [tuple(float(c) for c in r.split("\t")) for r in rows]
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _series() -> tuple[list[float], list[float], list[float]]:
    """Read (t, load, strain) columns of the real the local short-run file time series."""
    with (FIX / "short_data_series.csv").open(newline="", encoding="ascii") as fh:
        rows = list(csv.DictReader(fh))
    return (
        [float(r["t_s"]) for r in rows],
        [float(r["load_n"]) for r in rows],
        [float(r["strain"]) for r in rows],
    )


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
@needs_data
def test_fit_matches_vi_slope_intercept_r2_t95_n() -> None:
    v, h = _points()
    assert len(v) == 12
    res = fit_calibration(v, h)
    assert isinstance(res, Ok)
    f = res.danger_ok
    assert f.slope.value == pytest.approx(VI_TXT["slope"], rel=REL)
    assert f.intercept.value == pytest.approx(VI_TXT["intercept"], rel=REL)
    assert f.r2 == pytest.approx(VI_TXT["r2"], rel=REL)
    assert f.t95 == pytest.approx(VI_TXT["t95"], rel=REL)
    assert f.n == VI_TXT["n"]


# frob:tests python/sadi/labs/lctt/calibration.py::fit_calibration
@needs_data
def test_fit_matches_vi_standard_errors_at_full_precision() -> None:
    """The .txt se values (6.734580E-6, 1.970728E-5) differ from the VI's own full-precision
    csv-header values by ~1.7e-6 relative; we match the latter to < 1e-8 and the former to 2e-6."""
    v, h = _points()
    res = fit_calibration(v, h)
    assert isinstance(res, Ok)
    f = res.danger_ok
    assert f.se_slope == pytest.approx(VI_CSV["se_slope"], rel=1e-8)
    assert f.se_intercept == pytest.approx(VI_CSV["se_intercept"], rel=1e-6)
    assert f.se_slope == pytest.approx(VI_TXT["se_slope"], rel=2e-6)
    assert f.se_intercept == pytest.approx(VI_TXT["se_intercept"], rel=2e-6)


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
@needs_data
def test_real_short_data_slip_without_load_flags_only_load_steps() -> None:
    t, load, strain = _series()
    res = detect_slip(t, strain, 0.0)
    assert isinstance(res, Ok)
    rep: SlipReport = res.danger_ok
    flagged = [e.index for e in rep.events]
    _log.info("real short-run flagged without load: %s", flagged)
    assert flagged == [28, 31, 39]
    for i in flagged:
        assert load[i] != load[i - 1]  # every flagged jump sits on a load step


# frob:tests python/sadi/labs/lctt/slip.py::detect_slip
@needs_data
def test_real_short_data_slip_with_load_finds_no_slip() -> None:
    t, load, strain = _series()
    res = detect_slip(t, strain, 0.0, load=load, config=SlipConfig(load_tol=0.0))
    assert isinstance(res, Ok)
    assert res.danger_ok.events == ()


def test_tracked_docs_do_not_name_course_material() -> None:
    """Tracked docs must use generic wording for the course VI and lab data path."""
    root = Path(__file__).resolve().parents[4]
    banned = ("final_" + "project.vi", "EML" + "3301", "labview" + "/data")
    hits = [
        str(p)
        for p in (root / "docs").rglob("*.md")
        if p.name != "publishing.md" and any(b in p.read_text(encoding="utf-8") for b in banned)
    ]
    assert hits == []
