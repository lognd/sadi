"""LCTT CSV export and reader in the 49-column LabVIEW layout (domain.md section 4).

The document is DERIVED from session events (never the source of truth, invariant I7): the
events are recomputed through the loading, modulus and yield engines, rendered as a metadata
block, a blank line, the 49-column header and one row per logged point, and published through
the store exports primitive (tmp + fsync + no-replace rename, provenance sidecar). The reader
parses such a file back into a `CsvDocument` and into live events for post-processing.
Bytes: UTF-8, no BOM, CRLF after every row (see store/csv_export.py); the reader also accepts
LF and a BOM so files re-saved by other tools still load.
"""

# frob:ticket 01M6W7R3Q5RVEC8YFA37P8582F
# frob:ticket 01M6WX3GGD2VSGEY1GT2X49DSV
# frob:ticket 01M6WX3GJK2D59J39ZZS1J03DV
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

from sadi.core.export_api import UTF8_BOM, ExportResult, HasPath, render_csv, write_export
from sadi.labs.lctt.calibration import fit_calibration
from sadi.labs.lctt.live import (
    CalPoint,
    ExcludePoint,
    LiveConfig,
    LiveEvent,
    LoadPoint,
    SetWindow,
    SpecimenSetup,
    TareBlock,
    _e_window,  # noqa: PLC2701 - same-package: the live recompute's E window rule
    _fold,  # noqa: PLC2701 - same-package replay of the event log
)
from sadi.labs.lctt.loading import (
    STANDARD_G,
    LoadingError,
    LoadingInputs,
    compute_loading,
    pool_tare,
)
from sadi.labs.lctt.modulus import CurvePoint, fit_modulus
from sadi.labs.lctt.specimens import SpecimenRole, SpecimenSpec
from sadi.labs.lctt.yield_ import find_yield
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured, Provenance

_log = get_logger(__name__)

EXPORT_KIND = "lctt-csv"
# frob:ticket 01M6WX3GPBQA22B9AAJK7BN9MY
# frob:ticket 01M6WX3GMG3Z1WCC12V437XJK7
SCHEMA_VERSION = "5"  # v5: phase column (49) + per-phase L0; v4: 48 cols; v3: 42 cols
TITLE = "SADI LCTT tensile test"
NAN = float("nan")
ELASTIC = SpecimenRole.ELASTIC.value
PLASTIC = SpecimenRole.PLASTIC.value
_ROLE_BY_PHASE = {r.value: r for r in SpecimenRole}


class ExportCsvError(ErrorSet):
    """CSV export or read failure; details are logged, the description says what to do."""

    NotReady = "Calibration, tare, specimen and at least one point are needed before export"
    Compute = "A result could not be computed from the session events; see the log"
    Write = "The export could not be written; the recording itself is safe"
    BadFile = "The file is not a LabVIEW-schema LCTT CSV (missing blank line or header)"
    BadHeader = "The column header does not match the 49-column schema"
    BadCell = "A cell could not be parsed as its column type"
    Encoding = "The file is not valid UTF-8"


class PointRow(BaseModel):
    """One logged point; field order IS the 49-column header order."""

    model_config = ConfigDict(frozen=True)

    point_id: str
    index: int
    phase: str  # "elastic" / "plastic" specimen run; "" for legacy un-phased points
    elapsed_s: float  # seconds since load was applied; NaN when unknown
    volts: float
    u_volts: float
    volts_sd: float  # per-sample std dev of the raw volts; NaN when unknown
    mass_kg: float
    u_mass_kg: float
    delta_volts: float
    u_delta_volts: float  # sqrt(u_volts^2 + u_tare_v^2)
    height_m: float
    displacement_m: float
    u_displacement_m: float  # propagated from delta volts and calibration slope
    load_n: float
    u_load_n: float
    area_m2: float
    u_area_m2: float
    stress_pa: float
    u_stress_pa: float
    strain: float
    u_strain: float
    secant_modulus_pa: float
    u_secant_modulus_pa: float  # quotient propagation of stress and strain; NaN when undefined
    hanger_kg: float
    u_hanger_kg: float
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
    u_tare_v: float
    l0_m: float
    u_l0_m: float  # gauge length is an exact configured constant: 0
    diameter_m: float
    u_diameter_m: float
    intercept_m: float  # calibration intercept, repeated per row (schema 4)
    u_intercept_m: float  # calibration intercept standard error
    hanger_n: float  # hanger weight as force: hanger_kg * g
    u_hanger_n: float
    mass_n: float  # inventory-mass weight as force: mass_kg * g (excludes hanger)
    u_mass_n: float


COLUMNS: tuple[str, ...] = tuple(PointRow.model_fields)
_TYPES: tuple[Any, ...] = tuple(f.annotation for f in PointRow.model_fields.values())
assert len(COLUMNS) == 49, "the schema has exactly 49 columns"  # noqa: S101


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


def _cal_events(doc: CsvDocument) -> list[LiveEvent]:
    """Rebuild `CalPoint` events from consecutive `Cal point N` rows (stops at the first gap)."""
    out: list[LiveEvent] = []
    i = 1
    while True:
        v, h = doc.get_float(f"Cal point {i} volts (V)"), doc.get_float(f"Cal point {i} height (m)")
        if math.isnan(v) or math.isnan(h):
            break
        out.append(CalPoint(volts=v, height=h))
        i += 1
    _log.info("rebuilt %d calibration points from metadata", len(out))
    return out


def to_live_events(doc: CsvDocument) -> list[LiveEvent]:
    """Rebuild raw live events (tare, specimen, points, exclusions, window) for re-analysis.

    Raw calibration points are read from the numbered `Cal point N ...` metadata rows (files
    without them yield no `CalPoint`; the fit rows are then the only calibration record).
    """
    events: list[LiveEvent] = _cal_events(doc)
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
                      mass_kg=r.mass_kg, u_mass_kg=r.u_mass_kg, phase=r.phase,
                      t_since_load_s=None if math.isnan(r.elapsed_s) else r.elapsed_s,
                      volts_sd=None if math.isnan(r.volts_sd) else r.volts_sd)
        )  # fmt: skip
        if r.excluded:
            events.append(ExcludePoint(point_id=r.point_id))
    # The explicit window addresses the elastic (or only) curve, indexed within that group.
    active = [r for r in doc.rows if not r.excluded and r.phase != PLASTIC]
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


def _u_quotient(num: Measured, den: Measured) -> float:
    """Standard uncertainty of num/den for independent inputs; NaN when den is zero."""
    if not den.value:
        return NAN
    q = num.value / den.value
    return abs(q) * math.hypot(num.std_unc / num.value if num.value else 0.0,
                               den.std_unc / den.value)  # fmt: skip


class _Group:
    """One specimen's points with its gauge length, E fit and (plastic/legacy) yield."""

    def __init__(self, phase: str, loading: Any, active: list[str]) -> None:
        """Hold the phase key, its loading options and the active point ids (log order)."""
        self.phase, self.loading, self.active = phase, loading, active
        self.window: tuple[int, int] = (0, -1)
        self.mod: Result[Any, Any] | None = None
        self.yld: Result[Any, Any] | None = None

    @property
    def e_val(self) -> float:
        """The group's fitted modulus (Pa); NaN when no fit."""
        return self.mod.danger_ok.modulus.value if isinstance(self.mod, Ok) else NAN


def _group_options(cfg: LiveConfig, phase: str) -> Any:  # noqa: ANN401
    """Loading options for `phase`: its specimen's kind and L0, else the config's (legacy)."""
    role = _ROLE_BY_PHASE.get(phase)
    if role is None:
        return cfg.loading
    spec = SpecimenSpec(role=role)
    return cfg.loading.model_copy(update={"specimen": spec.kind, "l0": spec.l0_m})


def _fit_group(  # noqa: PLR0913
    g: _Group,
    loaded: dict[str, Any],
    window: SetWindow | None,
    cfg: LiveConfig,
    *,
    want_yield: bool,
) -> None:
    """Fit E on the group's active curve (explicit or auto window) and, if wanted, the yield."""
    curve = [
        CurvePoint(index=i, stress=loaded[pid].stress, strain=loaded[pid].strain)
        for i, pid in enumerate(g.active)
    ]
    if not curve:
        return
    g.window = _e_window(curve, window)
    g.mod = fit_modulus(curve, *g.window)
    if isinstance(g.mod, Err):
        _log.warning("export: %s modulus fit unavailable: %s", g.phase or "all", g.mod.danger_err)
        return
    if want_yield:
        g.yld = find_yield(curve, g.mod.danger_ok.modulus, cfg.offset)


def tare_report(
    means: Sequence[float], sds: Sequence[float], counts: Sequence[int]
) -> Result[Measured, LoadingError]:
    """Reported tare (V): pooled mean, standard error Sx/sqrt(N); one model for CSV and Results.

    This is the uncertainty OF THE TARE MEAN that every report (CSV rows incl. u_strain and
    u_stress, Results `tare`) states; the pooled 2 Sx (domain 3.2) is not used for CSV rows.
    """
    pooled = pool_tare(means, sds, counts)
    if isinstance(pooled, Err):
        return pooled
    p = pooled.danger_ok
    se = p.std_unc / 2.0 / math.sqrt(sum(counts))
    made = Measured.create(p.value, se, "V", provenance=Provenance(source="tare_report"))
    if isinstance(made, Err):
        _log.error("tare_report: invalid pooled tare")
        return Err(LoadingError.BadInput)
    return Ok(made.danger_ok)


def build_document(  # noqa: PLR0912, PLR0915 - one linear derivation, split would obscure it
    events: Sequence[LiveEvent],
    *,
    date: datetime,
    operator: str = "",
    description: str = "",
    config: LiveConfig | None = None,
) -> Result[CsvDocument, ExportCsvError]:
    """Derive the full document from raw session events (pure; `date` is passed for determinism).

    Mirrors the Results path: elastic points use L0 0.5 and give E/r2, plastic points use L0
    0.08313 and give yield (with the plastic curve's own modulus); each row names its phase. Points
    without a phase (legacy events) form one curve under the configured gauge length.
    """
    # frob:ticket 01M729642YCP4MRYBWBNQBYW7A
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
    report = tare_report([t.mean for t in st.tare], [t.sd for t in st.tare], [t.n for t in st.tare])
    if isinstance(cal, Err) or isinstance(pooled, Err) or isinstance(report, Err):
        _log.error("export: calibration or tare failed")
        return Err(ExportCsvError.Compute)
    fit, tare, spec = cal.danger_ok, pooled.danger_ok, st.specimen
    u_tare = report.danger_ok.std_unc
    # frob:ticket 01M72D3CTDED2MGDY721RSM8M4
    # One uncertainty model per row: the loading engine gets the same Sx/sqrt(N) tare as
    # u_delta_volts/u_displacement_m, so u_strain ~ u_displacement_m / l0_m (no 2 Sx in the CSV).
    row_tare = report.danger_ok
    dia, hang = (
        _m(spec.diameter, spec.u_diameter, "m", "dia"),
        _m(spec.hanger_kg, spec.u_hanger_kg, "kg", "hanger"),
    )
    if isinstance(dia, Err) or isinstance(hang, Err):
        return Err(ExportCsvError.Compute)
    phase_of = {pid: (p.phase if p.phase in _ROLE_BY_PHASE else "") for pid, p in st.points.items()}
    groups = {
        ph: _Group(ph, _group_options(cfg, ph),
                   [pid for pid in st.points if phase_of[pid] == ph and pid not in st.excluded])
        for ph in dict.fromkeys(phase_of.values())
    }  # fmt: skip
    loaded = {}
    for pid, p in st.points.items():
        volt, mass = _m(p.volts, p.u_volts, "V", "volts"), _m(p.mass_kg, p.u_mass_kg, "kg", "mass")
        if isinstance(volt, Err) or isinstance(mass, Err):
            return Err(ExportCsvError.Compute)
        res = compute_loading(
            LoadingInputs(voltage=volt.danger_ok, tare=row_tare, slope=fit.slope,
                          masses=(mass.danger_ok,), hanger=hang.danger_ok,
                          diameter=dia.danger_ok),
            groups[phase_of[pid]].loading,
        )  # fmt: skip
        if isinstance(res, Err):
            _log.error("export: loading failed for %s: %s", pid, res.danger_err)
            return Err(ExportCsvError.Compute)
        loaded[pid] = res.danger_ok
    for g in groups.values():
        # The explicit window addresses the elastic (or only) curve, as in the live recompute.
        _fit_group(g, loaded, st.window if g.phase != PLASTIC else None, cfg,
                   want_yield=g.phase != ELASTIC)  # fmt: skip
    e_group = groups.get(ELASTIC) or groups.get("")
    y_group = groups.get(PLASTIC) or groups.get("")
    mod = e_group.mod if e_group else None
    yld = y_group.yld if y_group else None
    rows: list[PointRow] = []
    for pid, p in st.points.items():
        lr, g = loaded[pid], groups[phase_of[pid]]
        u_dv = math.hypot(p.u_volts, u_tare)
        ai = g.active.index(pid) if pid in g.active else -1
        gm = g.mod if isinstance(g.mod, Ok) else None
        sat = gm is not None and ai in gm.danger_ok.saturated_points
        gy = g.yld if isinstance(g.yld, Ok) else None
        y_idx = gy.danger_ok.segment[1] if gy is not None else -1
        u_idx = gy.danger_ok.ultimate_index if gy is not None else -1
        rows.append(
            PointRow(
                point_id=pid, index=len(rows), phase=phase_of[pid],
                volts=p.volts, u_volts=p.u_volts,
                elapsed_s=NAN if p.t_since_load_s is None else p.t_since_load_s,
                volts_sd=NAN if p.volts_sd is None else p.volts_sd,
                mass_kg=p.mass_kg, u_mass_kg=p.u_mass_kg,
                delta_volts=p.volts - tare.value, u_delta_volts=u_dv,
                height_m=fit.slope.value * p.volts + fit.intercept.value,
                displacement_m=fit.slope.value * (p.volts - tare.value),
                u_displacement_m=math.hypot(
                    fit.slope.value * u_dv, (p.volts - tare.value) * fit.slope.std_unc
                ),
                load_n=lr.load.value, u_load_n=lr.load.std_unc,
                area_m2=lr.area.value, u_area_m2=lr.area.std_unc,
                stress_pa=lr.stress.value, u_stress_pa=lr.stress.std_unc,
                strain=lr.strain.value, u_strain=lr.strain.std_unc,
                secant_modulus_pa=lr.stress.value / lr.strain.value if lr.strain.value else NAN,
                u_secant_modulus_pa=_u_quotient(lr.stress, lr.strain),
                hanger_kg=spec.hanger_kg, u_hanger_kg=spec.u_hanger_kg,
                total_mass_kg=p.mass_kg + spec.hanger_kg,
                offset_line_pa=g.e_val * (lr.strain.value - cfg.offset),
                excluded=pid in st.excluded,
                in_window=ai >= 0 and g.window[0] <= ai <= g.window[1] and gm is not None,
                saturated=sat, settle_source="", is_yield=ai == y_idx and ai >= 0,
                is_ultimate=ai == u_idx and ai >= 0,
                low_r2=gm is not None and gm.danger_ok.low_r2,
                warnings=";".join(lr.warnings),
                slope_m_per_v=fit.slope.value, tare_v=tare.value, u_tare_v=u_tare,
                l0_m=g.loading.gauge_length, u_l0_m=0.0,
                diameter_m=spec.diameter, u_diameter_m=spec.u_diameter,
                intercept_m=fit.intercept.value, u_intercept_m=fit.intercept.std_unc,
                hanger_n=spec.hanger_kg * STANDARD_G, u_hanger_n=spec.u_hanger_kg * STANDARD_G,
                mass_n=p.mass_kg * STANDARD_G, u_mass_n=p.u_mass_kg * STANDARD_G,
            )
        )  # fmt: skip
    tare_n = sum(t.n for t in st.tare)
    tare_sd = pooled.danger_ok.std_unc / 2.0  # pool_tare: U_tare = 2 Sx (domain 3.2)
    l0s = (
        (e_group.loading.gauge_length if e_group else NAN),
        (y_group.loading.gauge_length if y_group else NAN),
    )
    meta = _meta(
        date,
        operator,
        description,
        cfg,
        report.danger_ok,
        tare_sd,
        tare_n,
        fit,
        spec,
        mod,
        yld,
        st.cal,
        l0s,
    )
    _log.info("export: built document with %d points in %d phase(s)", len(rows), len(groups))
    return Ok(CsvDocument(meta=tuple(meta), rows=tuple(rows)))


def _meta(  # noqa: PLR0913
    date: datetime, operator: str, description: str, cfg: LiveConfig,
    tare: Measured, tare_sd: float, tare_n: int, fit: Any, spec: SpecimenSetup, mod: Any,
    yld: Any, cal: Sequence[CalPoint] = (), l0s: tuple[float, float] = (NAN, NAN),
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
        ("Row uncertainty model", "U_tare = Sx/sqrt(N) for u_strain, u_stress, u_displacement_m"),
        ("Cal slope (m/V)", f(fit.slope.value)), ("Cal intercept (m)", f(fit.intercept.value)),
        ("Cal se slope", f(fit.se_slope)), ("Cal se intercept", f(fit.se_intercept)),
        ("Cal r2", f(fit.r2)), ("Cal t95", f(fit.t95)), ("Cal n", str(fit.n)),
        *[
            kv
            for i, c in enumerate(cal, start=1)
            for kv in ((f"Cal point {i} volts (V)", f(c.volts)),
                       (f"Cal point {i} height (m)", f(c.height)))
        ],
        ("Specimen diameter (m)", f(spec.diameter)),
        ("Specimen u diameter (m)", f(spec.u_diameter)),
        ("Elastic L0 (m)", f(l0s[0])), ("Plastic L0 (m)", f(l0s[1])),
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
