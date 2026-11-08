"""LCTT CSV export and reader in the 32-column LabVIEW layout (domain.md section 4).

The document is DERIVED from session events (never the source of truth, invariant I7): the
events are recomputed through the loading, modulus and yield engines, rendered as a metadata
block, a blank line, the 32-column header and one row per logged point, and published through
the store exports primitive (tmp + fsync + no-replace rename, provenance sidecar). The reader
parses such a file back into a `CsvDocument` and into live events for post-processing.
Bytes: UTF-8, no BOM, CRLF after every row (see store/csv_export.py); the reader also accepts
LF and a BOM so files re-saved by other tools still load.
"""

# frob:ticket 01M6W7R3Q5RVEC8YFA37P8582F
from __future__ import annotations

import csv
import io
import math
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.labs.lctt.calibration import fit_calibration
from sadi.labs.lctt.live import (
    ExcludePoint,
    LiveConfig,
    LiveEvent,
    LoadPoint,
    SetWindow,
    SpecimenSetup,
    TareBlock,
    _fold,  # noqa: PLC2701 - same-package replay of the event log
)
from sadi.labs.lctt.loading import LoadingInputs, compute_loading, pool_tare
from sadi.labs.lctt.modulus import CurvePoint, fit_modulus
from sadi.labs.lctt.yield_ import find_yield
from sadi.core.export_api import UTF8_BOM, ExportResult, HasPath, render_csv, write_export
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured, Provenance

_log = get_logger(__name__)

EXPORT_KIND = "lctt-csv"
SCHEMA_VERSION = "1"
TITLE = "SADI LCTT tensile test"
NAN = float("nan")


class ExportCsvError(ErrorSet):
    """CSV export or read failure; details are logged, the description says what to do."""

    NotReady = "Calibration, tare, specimen and at least one point are needed before export"
    Compute = "A result could not be computed from the session events; see the log"
    Write = "The export could not be written; the recording itself is safe"
    BadFile = "The file is not a LabVIEW-schema LCTT CSV (missing blank line or header)"
    BadHeader = "The column header does not match the 32-column schema"
    BadCell = "A cell could not be parsed as its column type"
    Encoding = "The file is not valid UTF-8"


class PointRow(BaseModel):
    """One logged point; field order IS the 32-column header order."""

    model_config = ConfigDict(frozen=True)

    point_id: str
    index: int
    volts: float
    u_volts: float
    mass_kg: float
    u_mass_kg: float
    delta_volts: float
    height_m: float
    displacement_m: float
    load_n: float
    u_load_n: float
    area_m2: float
    u_area_m2: float
    stress_pa: float
    u_stress_pa: float
    strain: float
    u_strain: float
    secant_modulus_pa: float
    hanger_kg: float
    total_mass_kg: float
    offset_line_pa: float
    excluded: bool
    in_window: bool
    saturated: bool
    settle_source: str
    is_yield: bool
    is_ultimate: bool
    low_r2: bool
    warnings: str
    slope_m_per_v: float
    tare_v: float
    l0_m: float


COLUMNS: tuple[str, ...] = tuple(PointRow.model_fields)
_TYPES: tuple[Any, ...] = tuple(f.annotation for f in PointRow.model_fields.values())
assert len(COLUMNS) == 32, "the LabVIEW schema has exactly 32 columns"  # noqa: S101


class CsvDocument(BaseModel):
    """Session-level data of one export: ordered metadata block plus the point rows."""

    model_config = ConfigDict(frozen=True)

    meta: tuple[tuple[str, str], ...]
    rows: tuple[PointRow, ...]

    def get(self, key: str) -> str | None:
        """Return the metadata value for `key`, or None when absent."""
        return dict(self.meta).get(key)

    def get_float(self, key: str) -> float:
        """Return a numeric metadata value (NaN when absent or unparsable)."""
        try:
            return float(self.get(key) or "nan")
        except ValueError:
            return NAN


def format_number(value: float) -> str:
    """Format at 10 significant digits with '.', NaN and Inf literal (domain.md section 4)."""
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Inf" if value > 0 else "-Inf"
    return f"{value:.10g}"


def _cell(value: object) -> str:
    """Render one cell: floats at 10 digits, bools as 1/0, everything else as text."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, float):
        return format_number(value)
    return str(value)


def _parse_cell(text: str, typ: Any) -> Any:  # noqa: ANN401
    """Parse a cell to its column type; raises ValueError on garbage (caller maps it)."""
    if typ is bool:
        if text not in ("0", "1"):
            raise ValueError(text)
        return text == "1"
    if typ is int:
        return int(text)
    if typ is float:
        return float(text)
    return text


def render_document(doc: CsvDocument) -> bytes:
    """Return the export bytes: metadata block, blank line, header, rows; UTF-8 + CRLF."""
    meta = [list(kv) for kv in doc.meta]
    body = [[]] + [list(COLUMNS)] + [[_cell(getattr(r, c)) for c in COLUMNS] for r in doc.rows]
    first, rest = meta[0], [*meta[1:], *body]
    return render_csv(first, rest)


def read_document(data: bytes) -> Result[CsvDocument, ExportCsvError]:
    """Parse export bytes (CRLF or LF, optional BOM) back into a `CsvDocument`."""
    try:
        text = data.removeprefix(UTF8_BOM).decode("utf-8")
    except UnicodeDecodeError as exc:
        _log.error("csv is not utf-8: %s", exc)
        return Err(ExportCsvError.Encoding)
    table = list(csv.reader(io.StringIO(text, newline="")))
    blank = next((i for i, r in enumerate(table) if not r), None)
    if blank is None or blank + 1 >= len(table):
        _log.error("csv has no blank separator or header")
        return Err(ExportCsvError.BadFile)
    if tuple(table[blank + 1]) != COLUMNS:
        _log.error("csv header mismatch: %d columns", len(table[blank + 1]))
        return Err(ExportCsvError.BadHeader)
    meta = tuple((r[0], r[1] if len(r) > 1 else "") for r in table[:blank])
    rows: list[PointRow] = []
    for lineno, raw in enumerate(table[blank + 2 :], start=blank + 3):
        if len(raw) != len(COLUMNS):
            _log.error("csv row %d has %d cells", lineno, len(raw))
            return Err(ExportCsvError.BadCell)
        try:
            vals = [_parse_cell(c, t) for c, t in zip(raw, _TYPES, strict=True)]
        except ValueError as exc:
            _log.error("csv row %d unparsable: %s", lineno, exc)
            return Err(ExportCsvError.BadCell)
        rows.append(PointRow(**dict(zip(COLUMNS, vals, strict=True))))
    _log.info("read csv: %d meta rows, %d points", len(meta), len(rows))
    return Ok(CsvDocument(meta=meta, rows=tuple(rows)))


def read_file(path: Path) -> Result[CsvDocument, ExportCsvError]:
    """Read and parse a LabVIEW-schema CSV file from disk."""
    try:
        return read_document(path.read_bytes())
    except OSError as exc:
        _log.error("cannot read %s: %s", path, exc)
        return Err(ExportCsvError.BadFile)


def to_live_events(doc: CsvDocument) -> list[LiveEvent]:
    """Rebuild raw live events (tare, specimen, points, exclusions, window) for re-analysis.

    Calibration points are not in the file (only the fit), so no `CalPoint` is produced; the
    caller supplies the slope/intercept metadata or the original calibration data.
    """
    events: list[LiveEvent] = []
    n, sd = doc.get_float("Tare n"), doc.get_float("Tare sd (V)")
    if not math.isnan(n):
        events.append(TareBlock(mean=doc.get_float("Tare mean (V)"), sd=sd, n=int(n)))
    if not math.isnan(doc.get_float("Specimen diameter (m)")):
        events.append(
            SpecimenSetup(
                diameter=doc.get_float("Specimen diameter (m)"),
                u_diameter=doc.get_float("Specimen u diameter (m)"),
                hanger_kg=doc.rows[0].hanger_kg if doc.rows else 0.0,
            )
        )
    for r in doc.rows:
        events.append(
            LoadPoint(point_id=r.point_id, volts=r.volts, u_volts=r.u_volts,
                      mass_kg=r.mass_kg, u_mass_kg=r.u_mass_kg)
        )  # fmt: skip
        if r.excluded:
            events.append(ExcludePoint(point_id=r.point_id))
    active = [r for r in doc.rows if not r.excluded]
    inwin = [i for i, r in enumerate(active) if r.in_window]
    if inwin:
        events.append(SetWindow(first=inwin[0], last=inwin[-1]))
    return events


def _m(value: float, unc: float, unit: str, src: str) -> Result[Measured, ExportCsvError]:
    """Build a Measured or report Compute."""
    made = Measured.create(value, unc, unit, provenance=Provenance(source=src))
    if isinstance(made, Err):
        _log.error("export: measured %s failed: %s", src, made.danger_err)
        return Err(ExportCsvError.Compute)
    return Ok(made.danger_ok)


def build_document(  # noqa: PLR0912, PLR0915 - one linear derivation, split would obscure it
    events: Sequence[LiveEvent],
    *,
    date: datetime,
    operator: str = "",
    description: str = "",
    config: LiveConfig | None = None,
) -> Result[CsvDocument, ExportCsvError]:
    """Derive the full document from raw session events (pure; `date` is passed for determinism)."""
    cfg = config or LiveConfig()
    folded = _fold(events)
    if isinstance(folded, Err):
        _log.error("export: event fold failed: %s", folded.danger_err)
        return Err(ExportCsvError.Compute)
    st = folded.danger_ok
    if not st.cal or not st.tare or st.specimen is None or not st.points:
        _log.warning("export: session not ready (cal/tare/specimen/points missing)")
        return Err(ExportCsvError.NotReady)
    cal = fit_calibration([c.volts for c in st.cal], [c.height for c in st.cal])
    pooled = pool_tare([t.mean for t in st.tare], [t.sd for t in st.tare], [t.n for t in st.tare])
    if isinstance(cal, Err) or isinstance(pooled, Err):
        _log.error("export: calibration or tare failed")
        return Err(ExportCsvError.Compute)
    fit, tare, spec = cal.danger_ok, pooled.danger_ok, st.specimen
    dia, hang = (
        _m(spec.diameter, spec.u_diameter, "m", "dia"),
        _m(spec.hanger_kg, spec.u_hanger_kg, "kg", "hanger"),
    )
    if isinstance(dia, Err) or isinstance(hang, Err):
        return Err(ExportCsvError.Compute)
    loaded = {}
    for pid, p in st.points.items():
        volt, mass = _m(p.volts, p.u_volts, "V", "volts"), _m(p.mass_kg, p.u_mass_kg, "kg", "mass")
        if isinstance(volt, Err) or isinstance(mass, Err):
            return Err(ExportCsvError.Compute)
        res = compute_loading(
            LoadingInputs(voltage=volt.danger_ok, tare=tare, slope=fit.slope,
                          masses=(mass.danger_ok,), hanger=hang.danger_ok,
                          diameter=dia.danger_ok),
            cfg.loading,
        )  # fmt: skip
        if isinstance(res, Err):
            _log.error("export: loading failed for %s: %s", pid, res.danger_err)
            return Err(ExportCsvError.Compute)
        loaded[pid] = res.danger_ok
    active = [pid for pid in st.points if pid not in st.excluded]
    curve = [
        CurvePoint(index=i, stress=loaded[pid].stress, strain=loaded[pid].strain)
        for i, pid in enumerate(active)
    ]
    first, last = (st.window.first, st.window.last) if st.window else (0, len(curve) - 1)
    mod = fit_modulus(curve, first, last)
    yld = find_yield(curve, mod.danger_ok.modulus, cfg.offset) if isinstance(mod, Ok) else None
    if isinstance(mod, Err):
        _log.warning("export: modulus fit unavailable: %s", mod.danger_err)
    e_val = mod.danger_ok.modulus.value if isinstance(mod, Ok) else NAN
    y_idx = yld.danger_ok.segment[1] if isinstance(yld, Ok) else -1
    u_idx = yld.danger_ok.ultimate_index if isinstance(yld, Ok) else -1
    low_r2 = mod.danger_ok.low_r2 if isinstance(mod, Ok) else False
    rows: list[PointRow] = []
    for pid, p in st.points.items():
        lr = loaded[pid]
        ai = active.index(pid) if pid in active else -1
        sat = isinstance(mod, Ok) and ai in mod.danger_ok.saturated_points
        rows.append(
            PointRow(
                point_id=pid, index=len(rows), volts=p.volts, u_volts=p.u_volts,
                mass_kg=p.mass_kg, u_mass_kg=p.u_mass_kg,
                delta_volts=p.volts - tare.value,
                height_m=fit.slope.value * p.volts + fit.intercept.value,
                displacement_m=fit.slope.value * (p.volts - tare.value),
                load_n=lr.load.value, u_load_n=lr.load.std_unc,
                area_m2=lr.area.value, u_area_m2=lr.area.std_unc,
                stress_pa=lr.stress.value, u_stress_pa=lr.stress.std_unc,
                strain=lr.strain.value, u_strain=lr.strain.std_unc,
                secant_modulus_pa=lr.stress.value / lr.strain.value if lr.strain.value else NAN,
                hanger_kg=spec.hanger_kg, total_mass_kg=p.mass_kg + spec.hanger_kg,
                offset_line_pa=e_val * (lr.strain.value - cfg.offset),
                excluded=pid in st.excluded,
                in_window=ai >= 0 and first <= ai <= last and isinstance(mod, Ok),
                saturated=sat, settle_source="", is_yield=ai == y_idx and ai >= 0,
                is_ultimate=ai == u_idx and ai >= 0, low_r2=low_r2,
                warnings=";".join(lr.warnings),
                slope_m_per_v=fit.slope.value, tare_v=tare.value, l0_m=cfg.loading.gauge_length,
            )
        )  # fmt: skip
    tare_n = sum(t.n for t in st.tare)
    tare_sd = tare.std_unc / 2.0  # pool_tare: U_tare = 2 Sx (domain 3.2)
    meta = _meta(date, operator, description, cfg, tare, tare_sd, tare_n, fit, spec, mod, yld)
    _log.info("export: built document with %d points", len(rows))
    return Ok(CsvDocument(meta=tuple(meta), rows=tuple(rows)))


def _meta(  # noqa: PLR0913
    date: datetime, operator: str, description: str, cfg: LiveConfig,
    tare: Measured, tare_sd: float, tare_n: int, fit: Any, spec: SpecimenSetup, mod: Any,
    yld: Any,
) -> list[tuple[str, str]]:  # fmt: skip
    """Ordered metadata block: title, run info, tare, calibration, specimen, modulus fit."""
    f = format_number
    ok_m, ok_y = isinstance(mod, Ok), isinstance(yld, Ok)
    mf = mod.danger_ok if ok_m else None
    return [
        ("Title", TITLE), ("Schema", SCHEMA_VERSION), ("Date", date.isoformat()),
        ("Operator", operator), ("Description", description),
        ("Tare mean (V)", f(tare.value)), ("Tare sd (V)", f(tare_sd)),
        ("Tare u (V)", f(tare.std_unc)), ("Tare n", str(tare_n)),
        ("Cal slope (m/V)", f(fit.slope.value)), ("Cal intercept (m)", f(fit.intercept.value)),
        ("Cal se slope", f(fit.se_slope)), ("Cal se intercept", f(fit.se_intercept)),
        ("Cal r2", f(fit.r2)), ("Cal t95", f(fit.t95)), ("Cal n", str(fit.n)),
        ("Specimen diameter (m)", f(spec.diameter)),
        ("Specimen u diameter (m)", f(spec.u_diameter)),
        ("Specimen L0 (m)", f(cfg.loading.gauge_length)),
        ("E (Pa)", f(mf.modulus.value if mf else NAN)),
        ("E se (Pa)", f(mf.std_error if mf else NAN)),
        ("E U95 (Pa)", f(mf.u95 if mf else NAN)),
        ("E r2", f(mf.r2 if mf else NAN)),
        ("E n", str(mf.n if mf else 0)),
        ("E window first", str(mf.first if mf else -1)),
        ("E window last", str(mf.last if mf else -1)),
        ("Offset strain", f(cfg.offset)),
        ("Yield stress (Pa)", f(yld.danger_ok.yield_stress.value if ok_y else NAN)),
        ("Yield strain", f(yld.danger_ok.yield_strain.value if ok_y else NAN)),
        ("Ultimate stress (Pa)", f(yld.danger_ok.ultimate_stress.value if ok_y else NAN)),
    ]  # fmt: skip


def export_csv(  # noqa: PLR0913
    session: HasPath,
    events: Sequence[LiveEvent],
    *,
    date: datetime,
    operator: str = "",
    description: str = "",
    basename: str = "lctt",
    config: LiveConfig | None = None,
    covers_seq: int | None = None,
) -> Result[ExportResult, ExportCsvError]:
    """Derive, render and atomically publish the CSV as a new numbered export with provenance."""
    built = build_document(
        events, date=date, operator=operator, description=description, config=config
    )
    if isinstance(built, Err):
        return Err(built.danger_err)
    payload = render_document(built.danger_ok)
    written = write_export(
        session, EXPORT_KIND, basename, "csv", payload,
        covers_seq=covers_seq, lab_module="lctt", now=date,
        parameters={"schema": SCHEMA_VERSION, "rows": len(built.danger_ok.rows)},
    )  # fmt: skip
    if written.is_err:
        _log.error("export: publish failed: %s", written.danger_err)
        return Err(ExportCsvError.Write)
    _log.info("export: published %s", written.danger_ok.path)
    return Ok(written.danger_ok)
