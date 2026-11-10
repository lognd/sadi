"""Tests for the LCTT 49-column CSV export, reader, round trip and byte policy."""

# frob:ticket 01M6W7R3Q5RVEC8YFA37P8582F
from __future__ import annotations

import math
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from typani import Err, Ok

from sadi.labs.lctt.export_csv import (
    COLUMNS,
    CsvDocument,
    ExportCsvError,
    build_document,
    export_csv,
    format_number,
    read_document,
    read_file,
    render_document,
    to_live_events,
)
from sadi.labs.lctt.live import (
    CalPoint,
    LiveEvent,
    LoadPoint,
    SpecimenSetup,
    TareBlock,
    recompute,
)
from sadi.store.session import SessionHandle, SessionMeta, create_session
from sadi.store.wal import WalConfig, WalWriter

NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=UTC)
REAL = Path(__file__).resolve().parents[2] / "fixtures" / "real_fp"


def _events(n: int = 8) -> list[LiveEvent]:
    """Synthetic session: linear LVDT cal, one tare block, a gently softening curve."""
    ev: list[LiveEvent] = [CalPoint(volts=v, height=0.08 + 0.002 * v) for v in range(1, 9)]
    ev.append(TareBlock(mean=0.5, sd=0.001, n=20))
    ev.append(SpecimenSetup(diameter=0.003, u_diameter=1e-5, hanger_kg=0.5, u_hanger_kg=1e-3))
    for i in range(n):
        ev.append(
            LoadPoint(point_id=f"p{i}", volts=0.5 + 0.01 * (i + 1) - 0.0002 * i * i,
                      mass_kg=0.2 * (i + 1), u_mass_kg=1e-4, u_volts=1e-4,
                      t_since_load_s=None if i == 0 else 30.0 + i, volts_sd=2e-4)
        )  # fmt: skip
    return ev


def _session(tmp_path: Path) -> SessionHandle:
    """Create a session whose WAL has a (empty) verified segment so provenance can be scanned."""
    h = create_session(tmp_path, SessionMeta(slug="x"), NOW).danger_ok
    w = WalWriter.open(h.path / "wal", uuid.UUID(h.manifest.session_uuid), 1, WalConfig())
    w.danger_ok.close().expect("close")
    return h


def _doc() -> CsvDocument:
    """Build the synthetic document, failing the test if derivation fails."""
    built = build_document(_events(), date=NOW, operator="op", description="d, with comma")
    assert isinstance(built, Ok), built
    return built.danger_ok


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_header_is_48_columns_and_block_layout() -> None:
    data = render_document(_doc())
    lines = data.decode("utf-8").split("\r\n")
    blank = lines.index("")
    assert lines[blank + 1].split(",") == list(COLUMNS)
    assert len(COLUMNS) == 49
    assert lines[0] == "Title,SADI LCTT tensile test"
    assert all(len(r.split(",")) == 49 for r in lines[blank + 2 : -1])
    assert len(lines[blank + 2 : -1]) == 8
    meta = dict(_doc().meta)
    for key in ("Date", "Operator", "Description", "Tare mean (V)", "Cal slope (m/V)", "E (Pa)"):
        assert key in meta


# frob:tests python/sadi/labs/lctt/export_csv.py::build_document
def test_values_match_live_recompute() -> None:
    doc = _doc()
    res = recompute(_events())
    assert isinstance(res, Ok)
    vals = {v.name: v for v in res.danger_ok.values}
    assert doc.get_float("E (Pa)") == pytest.approx(vals["E"].value, rel=1e-6)
    assert doc.get_float("Cal slope (m/V)") == pytest.approx(vals["slope"].value, rel=1e-6)


# frob:tests python/sadi/labs/lctt/export_csv.py::read_document
def test_synthetic_round_trip_field_by_field() -> None:
    doc = _doc()
    back = read_document(render_document(doc))
    assert isinstance(back, Ok)
    got = back.danger_ok
    assert [k for k, _ in got.meta] == [k for k, _ in doc.meta]
    assert len(got.rows) == len(doc.rows)
    for a, b in zip(doc.rows, got.rows, strict=True):
        for col in COLUMNS:
            x, y = getattr(a, col), getattr(b, col)
            if isinstance(x, float):
                assert (math.isnan(x) and math.isnan(y)) or y == pytest.approx(x, rel=1e-9)
            else:
                assert x == y
    assert render_document(got) == render_document(doc)  # idempotent at 10 digits


# frob:tests python/sadi/labs/lctt/export_csv.py::to_live_events
def test_reader_rebuilds_events_for_post_processing() -> None:
    doc = _doc()
    events = to_live_events(doc)
    assert sum(isinstance(e, LoadPoint) for e in events) == 8
    assert any(isinstance(e, TareBlock) for e in events)
    assert any(isinstance(e, SpecimenSetup) for e in events)


# frob:tests python/sadi/labs/lctt/export_csv.py::format_number
def test_number_format_literals() -> None:
    assert format_number(math.nan) == "NaN"
    assert format_number(math.inf) == "Inf"
    assert format_number(-math.inf) == "-Inf"
    assert format_number(1 / 3) == "0.3333333333"
    assert format_number(1234567.891234) == "1234567.891"


# frob:tests python/sadi/labs/lctt/export_csv.py::render_document
def test_bytes_are_utf8_crlf_without_bom_and_ascii() -> None:
    data = render_document(_doc())
    assert not data.startswith(b"\xef\xbb\xbf")
    assert data.endswith(b"\r\n")
    assert data.count(b"\n") == data.count(b"\r\n")
    data.decode("ascii")


# frob:tests python/sadi/labs/lctt/export_csv.py::read_document
def test_reader_accepts_lf_and_bom_and_rejects_bad_input() -> None:
    data = render_document(_doc())
    lf = read_document(b"\xef\xbb\xbf" + data.replace(b"\r\n", b"\n"))
    assert isinstance(lf, Ok)
    assert len(lf.danger_ok.rows) == 8
    bad = read_document(data.replace(b"point_id", b"pid", 1))
    assert isinstance(bad, Err)
    assert bad.danger_err is ExportCsvError.BadHeader
    enc = read_document(b"\xff\xfe\x00")
    assert isinstance(enc, Err)
    assert enc.danger_err is ExportCsvError.Encoding
    nofile = read_document(b"a,b\r\n")
    assert isinstance(nofile, Err)
    assert nofile.danger_err is ExportCsvError.BadFile


# frob:tests python/sadi/labs/lctt/export_csv.py::export_csv
def test_export_is_atomic_numbered_and_never_overwrites(tmp_path: Path) -> None:
    h = _session(tmp_path)
    first = export_csv(h, _events(), date=NOW, basename="run 1/../x")
    second = export_csv(h, _events(), date=NOW, basename="run 1/../x")
    assert isinstance(first, Ok)
    assert isinstance(second, Ok)
    p1, p2 = first.danger_ok.path, second.danger_ok.path
    assert p1 != p2
    assert "/" not in p1.name
    assert p1.parent.name == "lctt-csv"
    assert first.danger_ok.sidecar is not None
    assert not list(p1.parent.glob(".*tmp*"))
    parsed = read_file(p1)
    assert isinstance(parsed, Ok)
    assert p1.read_bytes() == p2.read_bytes()
    assert p1.read_bytes().count(b"\r\n") == p1.read_bytes().count(b"\n")


# frob:tests python/sadi/labs/lctt/export_csv.py::export_csv
def test_not_ready_without_inputs(tmp_path: Path) -> None:
    h = _session(tmp_path)
    res = export_csv(h, [], date=NOW)
    assert isinstance(res, Err)
    assert res.danger_err is ExportCsvError.NotReady


# frob:tests python/sadi/labs/lctt/export_csv.py::read_file
@pytest.mark.skipif(
    not (REAL / "short_data.csv").is_file(),
    reason="local lab data (real_fp fixtures) not present; kept out of git",
)
def test_private_short_run_file_round_trips_field_by_field() -> None:
    raw = (REAL / "short_data.csv").read_bytes()
    parsed = read_document(raw)
    assert isinstance(parsed, Ok)
    again = read_document(render_document(parsed.danger_ok))
    assert isinstance(again, Ok)
    for a, b in zip(parsed.danger_ok.rows, again.danger_ok.rows, strict=True):
        assert a.stress_pa == pytest.approx(b.stress_pa, rel=1e-9)


# frob:ticket 01M6WX3GGD2VSGEY1GT2X49DSV
# frob:tests python/sadi/labs/lctt/export_csv.py::PointRow
def test_elapsed_and_sd_columns_round_trip() -> None:
    doc = _doc()
    assert doc.get("Schema") == "5"
    assert math.isnan(doc.rows[0].elapsed_s)  # unknown elapsed time is NaN, not 0
    assert doc.rows[3].elapsed_s == pytest.approx(33.0)
    assert all(r.volts_sd == pytest.approx(2e-4) for r in doc.rows)
    back = read_document(render_document(doc)).danger_ok
    assert back.rows[3].elapsed_s == pytest.approx(33.0)
    assert back.rows[3].volts_sd == pytest.approx(2e-4)
    lp = [e for e in to_live_events(back) if isinstance(e, LoadPoint)]
    assert lp[0].t_since_load_s is None and lp[3].t_since_load_s == pytest.approx(33.0)
    assert lp[3].volts_sd == pytest.approx(2e-4)


# frob:ticket 01M6WX3GJK2D59J39ZZS1J03DV
# frob:tests python/sadi/labs/lctt/export_csv.py::PointRow
def test_uncertainty_columns_round_trip_and_values() -> None:
    doc = _doc()
    back = read_document(render_document(doc)).danger_ok
    for a, b in zip(doc.rows, back.rows, strict=True):
        for col in ("u_delta_volts", "u_displacement_m", "u_hanger_kg", "u_tare_v",
                    "u_l0_m", "u_diameter_m", "u_secant_modulus_pa"):  # fmt: skip
            assert getattr(b, col) == pytest.approx(getattr(a, col), rel=1e-9, nan_ok=True)
    r = doc.rows[3]
    assert r.u_delta_volts == pytest.approx(math.hypot(r.u_volts, r.u_tare_v))
    assert r.u_displacement_m > 0 and r.u_l0_m == 0.0 and r.u_diameter_m >= 0
    assert r.u_secant_modulus_pa > 0
    assert r.diameter_m == doc.get_float("Specimen diameter (m)")


# frob:ticket 01M6WX3GJK2D59J39ZZS1J03DV
# frob:tests python/sadi/labs/lctt/export_csv.py::read_document
def test_older_schema_header_rejected() -> None:
    text = render_document(_doc()).decode("utf-8")
    old = text.replace(",u_delta_volts", "", 1).encode("utf-8")
    res = read_document(old)
    assert isinstance(res, Err) and res.danger_err == ExportCsvError.BadHeader


# frob:ticket 01M6WX3GPBQA22B9AAJK7BN9MY
# frob:tests python/sadi/labs/lctt/export_csv.py::to_live_events
def test_calibration_points_round_trip_to_cal_events() -> None:
    orig = [e for e in _events() if isinstance(e, CalPoint)]
    assert orig
    back = read_document(render_document(_doc())).danger_ok
    got = [e for e in to_live_events(back) if isinstance(e, CalPoint)]
    assert len(got) == len(orig)
    for a, b in zip(orig, got, strict=True):
        assert b.volts == pytest.approx(a.volts, rel=1e-9)
        assert b.height == pytest.approx(a.height, rel=1e-9)
    assert recompute(to_live_events(back)) is not None


# frob:ticket 01M6WX3GPBQA22B9AAJK7BN9MY
# frob:tests python/sadi/labs/lctt/export_csv.py::to_live_events
def test_file_without_cal_point_rows_yields_no_cal_events() -> None:
    doc = _doc()
    stripped = CsvDocument(meta=tuple(kv for kv in doc.meta if not kv[0].startswith("Cal point")),
                           rows=doc.rows)  # fmt: skip
    assert not any(isinstance(e, CalPoint) for e in to_live_events(stripped))


# frob:ticket 01M6WX3GMG3Z1WCC12V437XJK7
# frob:tests python/sadi/labs/lctt/export_csv.py::PointRow
def test_intercept_and_force_columns_alongside_mass_columns() -> None:
    doc = _doc()
    back = read_document(render_document(doc)).danger_ok
    r = back.rows[2]
    g = 9.80665
    assert r.intercept_m == pytest.approx(doc.get_float("Cal intercept (m)"))
    assert r.hanger_n == pytest.approx(r.hanger_kg * g)
    assert r.mass_n == pytest.approx(r.mass_kg * g)
    assert r.u_mass_n == pytest.approx(r.u_mass_kg * g)
    assert r.load_n == pytest.approx(r.total_mass_kg * g, rel=1e-6)
    assert {"mass_kg", "hanger_kg", "slope_m_per_v", "tare_v"} <= set(COLUMNS)
