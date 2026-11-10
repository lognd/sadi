"""LCTT lab: the seven-step two-specimen workflow and the combined E + yield results."""

# frob:ticket 01M6W7R3RXWS1WSH3TPXMK16Q2

from __future__ import annotations

import math
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.core.errors import ComputeCode, ComputeError
from sadi.core.lab import (
    AnalysisResult,
    CaptureKind,
    ExportFormat,
    ExportFormatId,
    LabBudget,
    LabId,
    StepId,
    StepSpec,
)
from sadi.core.models import CapturedPoint, Phase, Quantity, RunState
from sadi.core.point_inputs import (
    PHASE_CALIBRATION,
    PHASE_SETUP,
    CalibrationInputs,
    ClampInputs,
    LoadInputs,
    PointInputs,
    SpecimenInputs,
    TareInputs,
    parse_inputs,
)
from sadi.core.results import ResultValue
from sadi.labs.lctt.budgets import nominal_budgets
from sadi.labs.lctt.calibration import MIN_POINTS, fit_calibration
from sadi.labs.lctt.clamp_check import (
    ADVICE_RETIGHTEN,
    ClampCheckConfig,
    clamp_status,
    setup_subcheck,
)
from sadi.labs.lctt.export_csv import build_document, render_document, tare_report
from sadi.labs.lctt.figure_data import figure_data
from sadi.labs.lctt.live import (
    CalPoint,
    ExcludePoint,
    LiveConfig,
    LiveEvent,
    LoadPoint,
    OverridePoint,
    SetWindow,
    SpecimenSetup,
    TareBlock,
    recompute,
)
from sadi.labs.lctt.loading import (
    LONG_L0_M,
    SHORT_L0_M,
    STANDARD_G,
    cross_area,
    load_force,
    strain,
    stress,
)
from sadi.labs.lctt.modulus import secant_modulus
from sadi.labs.lctt.specimens import SpecimenRole, SpecimenSpec
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured

_log = get_logger(__name__)

#: Results taken from the long (elastic) specimen.
ELASTIC_RESULTS = ("E", "r2")
#: Results taken from the short (plastic) specimen.
PLASTIC_RESULTS = ("yield_stress",)
#: Nominal wire diameter (m) used for stress until the specimen geometry is supplied.
NOMINAL_DIAMETER_M = 0.006
#: Relative standard uncertainty charged to the assumed diameter (so results never show +/- 0).
ASSUMED_DIAMETER_REL_UNC = 0.2
#: Calibration quality-gate thresholds (r^2 floor, outlier residual in standard errors).
CAL_MIN_R2 = 0.999
CAL_OUTLIER_K = 3.0


class LabError(ErrorSet):
    """Two-specimen workflow failure; the description says what to fix."""

    WrongRole = "Run roles must be one elastic (long) and one plastic (short) specimen"
    BadInput = "A captured input cannot be turned into a run event; check the entered values"
    Recompute = "A specimen run could not be computed; see the log for the failing step"


def _guide(text: str):  # type: ignore[no-untyped-def]  # noqa: ANN202
    """Build a guidance hook returning fixed operator text."""

    def guidance(state: RunState) -> str:
        """Return the fixed guidance text for this step."""
        return text

    return guidance


def _worst_calibration_point(
    volts: list[float], heights: list[float], residuals: Sequence[float]
) -> int:
    """Index of the point whose removal gives the best r2 (leave-one-out); residual fallback."""
    n = len(volts)
    best, best_r2 = max(range(n), key=lambda i: abs(residuals[i])), -math.inf
    if n <= MIN_POINTS:
        return best
    for i in range(n):
        sub = fit_calibration(volts[:i] + volts[i + 1 :], heights[:i] + heights[i + 1 :])
        if sub.is_ok and sub.danger_ok.r2 > best_r2:
            best, best_r2 = i, sub.danger_ok.r2
    return best


def calibration_gate(points: list[dict[str, Any]]) -> str | None:
    """Quality gate for the calibrate step: a valid, tight, monotone LVDT fit with no outlier."""
    # frob:ticket 01M7230XMB52H0AA8ETNQ8RBPX
    volts: list[float] = []
    heights: list[float] = []
    for inputs in points:
        parsed = parse_inputs(PHASE_CALIBRATION, inputs)
        item = parsed.danger_ok if parsed.is_ok else None
        if isinstance(item, CalibrationInputs):
            volts.append(item.volts)
            heights.append(item.height)
    fit = fit_calibration(volts, heights)
    if fit.is_err:
        return f"Calibration has no valid fit: {fit.danger_err.description}"
    f = fit.danger_ok
    worst = _worst_calibration_point(volts, heights, f.residuals)
    where = (
        f"point {worst + 1} (volts {volts[worst]:g}, height {heights[worst]:g} m) fits worst; "
        "exclude or recapture it (a height typed in mm instead of m is the usual cause)"
    )
    if f.slope.value <= 0:
        return f"Calibration slope is not positive ({f.slope.value:g} m/V); {where}"
    if f.r2 < CAL_MIN_R2:
        return f"Calibration fit is poor (r2 {f.r2:.4f}, need at least {CAL_MIN_R2}); {where}"
    if f.se_regression > 0 and abs(f.residuals[worst]) > CAL_OUTLIER_K * f.se_regression:
        return f"Calibration has an outlier; {where}"
    return None


def clamp_gate(config: ClampCheckConfig | None = None):  # type: ignore[no-untyped-def]  # noqa: ANN202
    """Build the setup-step gate: the recorded clamp-check cycles must all pass."""
    # frob:ticket 01M71WYRA3SN64B56Z6G13SHSE
    cfg = config or ClampCheckConfig()

    def gate(points: list[dict[str, Any]]) -> str | None:
        """Return a message when the clamp check has not passed, else None."""
        cycles: list[tuple[float, float, int]] = []
        for inputs in points:
            parsed = parse_inputs(PHASE_SETUP, inputs)
            item = parsed.danger_ok if parsed.is_ok else None
            if isinstance(item, ClampInputs):
                cycles.append((item.zero_before, item.zero_after, item.slip_events))
        status = clamp_status(cycles, cfg)
        if status.passed is False:
            return (
                "The clamp-slip check failed (a cycle slipped or the zero did not return). "
                f"{ADVICE_RETIGHTEN} Repeat the cycles (exclude the failed ones), "
                "or skip the step explicitly to proceed without a passing check."
            )
        return None

    return gate


def setup_step(config: ClampCheckConfig | None = None) -> StepSpec:
    """Build the Setup step hosting the clamp-slip sub-check; done after one capture per cycle."""
    # frob:ticket 01M6WJ8R4E0K2Z5K5KZJTJA6QM
    cfg = config or ClampCheckConfig()
    sub = setup_subcheck(cfg)
    _log.debug("lctt setup step: sub-check %s, min_points=%d", sub.check_id, cfg.cycles)
    return StepSpec(
        id=StepId(sub.step_id),
        title="Setup: " + sub.title,
        phase=Phase.SETUP,
        capture=CaptureKind.DEVICE_POINTS,
        guidance=_guide(sub.guidance),
        min_points=cfg.cycles,
        complete_check=clamp_gate(cfg),
    )


def lctt_steps() -> list[StepSpec]:
    """Return the ordered steps: Setup, Calibrate, Tare, Elastic, Plastic, Results, Export."""
    return [
        setup_step(),
        StepSpec(
            id=StepId("calibrate"),
            title="LVDT calibration",
            phase=Phase.CALIBRATION,
            capture=CaptureKind.DEVICE_POINTS,
            guidance=_guide("Step the LVDT through known heights and capture each."),
            complete_check=calibration_gate,
        ),
        StepSpec(
            id=StepId("tare"),
            title="Tare",
            phase=Phase.TARE,
            capture=CaptureKind.DEVICE_POINTS,
            guidance=_guide("With no load on the wire, capture the zero-load LVDT voltage."),
        ),
        StepSpec(
            id=StepId("elastic"),
            title="Elastic run (long specimen)",
            phase=Phase.ELASTIC,
            capture=CaptureKind.DEVICE_POINTS,
            guidance=_guide("Load the long specimen in increments; capture each settled point."),
        ),
        StepSpec(
            id=StepId("plastic"),
            title="Plastic run (short specimen)",
            phase=Phase.PLASTIC,
            capture=CaptureKind.DEVICE_POINTS,
            guidance=_guide("Load the short specimen past yield; capture each settled point."),
        ),
        StepSpec(
            id=StepId("results"),
            title="Results",
            phase=Phase.RESULTS,
            capture=CaptureKind.NONE,
            guidance=_guide("Review E (long specimen) and yield (short specimen) with sources."),
        ),
        StepSpec(
            id=StepId("export"),
            title="Export",
            phase=Phase.EXPORT,
            capture=CaptureKind.NONE,
            guidance=_guide("Export the run; the files record which specimen gave which result."),
        ),
    ]


class SpecimenRun(BaseModel):
    """One specimen's run: its spec, its inputs and an optional inclusive E window."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    spec: SpecimenSpec
    inputs: tuple[PointInputs, ...]
    window: tuple[int, int] | None = None


class SourcedValue(BaseModel):
    """A reported result together with the specimen that supplied it."""

    model_config = ConfigDict(frozen=True)

    result: ResultValue
    role: SpecimenRole
    source: str
    l0_m: float


class TwoSpecimenResults(BaseModel):
    """E from the long sample, yield from the short sample, each naming its source specimen."""

    model_config = ConfigDict(frozen=True)

    values: tuple[SourcedValue, ...] = ()
    pending: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def get(self, name: str) -> SourcedValue | None:
        """Return the named sourced result, or None when it is not computable yet."""
        return next((v for v in self.values if v.result.name == name), None)


def events_from_inputs(
    inputs: Sequence[PointInputs], prefix: str
) -> Result[list[LiveEvent], LabError]:
    """Map core typed point inputs to live events; load ids are `<prefix>-<n>` per run."""
    out: list[LiveEvent] = []
    n_load = 0
    for item in inputs:
        if isinstance(item, CalibrationInputs):
            out.append(CalPoint(volts=item.volts, height=item.height))
        elif isinstance(item, TareInputs):
            out.append(TareBlock(mean=item.mean, sd=item.sd, n=item.n))
        elif isinstance(item, SpecimenInputs):
            out.append(
                SpecimenSetup(
                    diameter=item.diameter,
                    u_diameter=item.u_diameter,
                    hanger_kg=item.hanger_kg,
                    u_hanger_kg=item.u_hanger_kg,
                )
            )
        elif isinstance(item, LoadInputs):
            out.append(
                LoadPoint(
                    point_id=f"{prefix}-{n_load}",
                    phase=item.phase,  # frob:ticket 01M729642YCP4MRYBWBNQBYW7A
                    volts=item.volts,
                    u_volts=item.u_volts,
                    volts_sd=item.volts_sd,  # frob:ticket 01M6WX3GGD2VSGEY1GT2X49DSV
                    mass_kg=item.mass_kg,
                    u_mass_kg=item.u_mass_kg,
                )
            )
            n_load += 1
        else:  # pragma: no cover - PointInputs is a closed union
            _log.error("events_from_inputs: unexpected input %r", item)
            return Err(LabError.BadInput)
    _log.debug("events_from_inputs[%s]: %d inputs -> %d events", prefix, len(inputs), len(out))
    return Ok(out)


def _run_results(
    run: SpecimenRun, shared: Sequence[PointInputs]
) -> Result[tuple[dict[str, ResultValue], list[str], list[str]], LabError]:
    """Recompute one run (shared calibration and tare inputs first); return values/pending/notes."""
    events = events_from_inputs([*shared, *run.inputs], run.spec.role.value)
    if isinstance(events, Err):
        return Err(events.danger_err)
    evs = events.danger_ok
    if run.window is not None:
        evs.append(SetWindow(first=run.window[0], last=run.window[1]))
    done = recompute(evs, LiveConfig(loading=run.spec.loading_options()))
    if isinstance(done, Err):
        _log.warning("run %s: recompute failed: %s", run.spec.role, done.danger_err)
        return Err(LabError.Recompute)
    rs = done.danger_ok
    return Ok(({v.name: v for v in rs.values}, list(rs.pending), list(rs.notes)))


def combine_runs(
    elastic: SpecimenRun, plastic: SpecimenRun, shared: Sequence[PointInputs] = ()
) -> Result[TwoSpecimenResults, LabError]:
    """Combine E/r2 from the long run with yield from the short run, stating each source.

    `shared` holds calibration and tare inputs used by both runs, so a lab that supplies the
    core inventory (heights for calibration, masses for the load) never re-enters them.
    """
    if (
        elastic.spec.role is not SpecimenRole.ELASTIC
        or plastic.spec.role is not SpecimenRole.PLASTIC
    ):
        _log.warning("combine_runs: roles %s/%s", elastic.spec.role, plastic.spec.role)
        return Err(LabError.WrongRole)
    values: list[SourcedValue] = []
    pending: list[str] = []
    notes: list[str] = []
    for run, wanted in ((elastic, ELASTIC_RESULTS), (plastic, PLASTIC_RESULTS)):
        got = _run_results(run, shared)
        if isinstance(got, Err):
            return Err(got.danger_err)
        vals, pend, nts = got.danger_ok
        for name in wanted:
            if name in vals:
                values.append(
                    SourcedValue(
                        result=vals[name],
                        role=run.spec.role,
                        source=run.spec.name,
                        l0_m=run.spec.l0_m,
                    )  # fmt: skip
                )
            else:
                pending.append(name)
        notes += [f"{run.spec.role.value}: {n}" for n in nts if n.split(":")[0] in wanted]
    _log.info("combine_runs: %d values, pending=%s", len(values), pending)
    return Ok(TwoSpecimenResults(values=tuple(values), pending=tuple(pending), notes=tuple(notes)))


# frob:ticket 01M6WVADB5YKXAVC43CQNBQVJW
def _write_csv(run: RunState, result: AnalysisResult) -> Result[bytes, ComputeError]:
    """Render the 42-column lctt CSV from the raw session events carried on `run` (in memory)."""
    events = [e for e in run.events if isinstance(e, _LIVE_EVENT_TYPES)]
    doc = build_document(events, date=datetime.now(UTC))
    if isinstance(doc, Err):
        _log.warning("lctt csv export refused: %s", doc.danger_err)
        return Err(ComputeError(code=ComputeCode.TOO_FEW_POINTS, detail=str(doc.danger_err)))
    return Ok(render_document(doc.danger_ok))


_LIVE_EVENT_TYPES = (
    CalPoint, TareBlock, SpecimenSetup, LoadPoint, OverridePoint, ExcludePoint, SetWindow
)  # fmt: skip


#: The lctt-csv export format: project-defined 42-column layout, see docs/lctt/export-csv.md.
# frob:ticket 01M6WYB1R6FYQ95T8SDQ62G869
CSV_FORMAT = ExportFormat(
    id=ExportFormatId("lctt-csv"),
    title="LCTT CSV",
    media_type="text/csv",
    writer=_write_csv,
)


# frob:ticket 01M6WVADB5YKXAVC43CQNBQVJW
def _write_figure_json(run: RunState, result: AnalysisResult) -> Result[bytes, ComputeError]:
    """Render the calibration and stress-strain series as JSON from the raw session events."""
    events = [e for e in run.events if isinstance(e, _LIVE_EVENT_TYPES)]
    data = figure_data(events)
    if isinstance(data, Err):
        return Err(data.danger_err)
    return Ok(data.danger_ok.model_dump_json(indent=2).encode("utf-8"))


#: The lctt-figure-json export format: series behind the calibration and stress-strain plots.
FIGURE_FORMAT = ExportFormat(
    id=ExportFormatId("lctt-figure-json"),
    title="LCTT figure data (JSON)",
    media_type="application/json",
    writer=_write_figure_json,
)


class LoadingContext(BaseModel):
    """Geometry and calibration the core points do not carry; absent slope/tare omit strain."""

    model_config = ConfigDict(frozen=True)

    diameter_m: float = NOMINAL_DIAMETER_M
    u_diameter_m: float = ASSUMED_DIAMETER_REL_UNC * NOMINAL_DIAMETER_M
    hanger_kg: float = 0.0
    l0_m: float = SHORT_L0_M
    slope_m_per_v: float | None = None
    tare_v: float | None = None


def context_from_inputs(inputs: Sequence[PointInputs]) -> LoadingContext:
    """Derive geometry, tare and calibration slope from a session's typed inputs (pure).

    The last specimen entry gives diameter and hanger mass, the last tare block the tare volts,
    three or more calibration points a fitted slope, and the last load point's phase the gauge
    length (elastic = long). Anything missing keeps the nominal default or omits strain.
    """
    # frob:ticket 01M7230XMB52H0AA8ETNQ8RBPX
    ctx: dict[str, Any] = {}
    cal_v: list[float] = []
    cal_h: list[float] = []
    for item in inputs:
        if isinstance(item, SpecimenInputs):
            ctx.update(
                diameter_m=item.diameter, u_diameter_m=item.u_diameter, hanger_kg=item.hanger_kg
            )
        elif isinstance(item, TareInputs):
            ctx["tare_v"] = item.mean
        elif isinstance(item, CalibrationInputs):
            cal_v.append(item.volts)
            cal_h.append(item.height)
        else:  # LoadInputs
            ctx["l0_m"] = LONG_L0_M if item.phase == SpecimenRole.ELASTIC.value else SHORT_L0_M
    if len(cal_v) >= MIN_POINTS:
        fit = fit_calibration(cal_v, cal_h)
        if isinstance(fit, Ok):
            ctx["slope_m_per_v"] = fit.danger_ok.slope.value
        else:
            _log.info("lctt context: calibration fit unavailable: %s", fit.danger_err.name)
    _log.debug("lctt context from %d inputs: keys=%s", len(inputs), sorted(ctx))
    return LoadingContext(**ctx)


def diameter_assumed_note() -> str:
    """Result note stating the nominal diameter was used because none was entered."""
    return (
        f"diameter assumed {NOMINAL_DIAMETER_M * 1e3:g} mm "
        f"(+/- {ASSUMED_DIAMETER_REL_UNC * 100:g} %) because no specimen diameter was entered; "
        "enter the measured diameter on the Tare step"
    )


def _meas(value: float, unc: float, unit: str) -> Measured | None:
    """Build a Measured or None (logged) when the value is not a valid measurement."""
    made = Measured.create(value, unc, unit)
    if isinstance(made, Err):
        _log.warning("lctt recompute: bad %s measurement %g: %s", unit, value, made.danger_err)
        return None
    return made.danger_ok


def _quantity(m: Measured, unit: str) -> Quantity:
    """Project a Measured onto the core Quantity (value and standard uncertainty)."""
    return Quantity(value=m.value, standard_uncertainty=m.std_unc, unit=unit)


#: Stated systematic allowance (3 % relative, added in quadrature to the fitted E uncertainty)
#: for creep / incomplete settling. It is NOT a fitted creep correction: synthetic copper
#: creeps about 1-4 % of the elastic strain over the loading range, biasing E low, and this
#: widens the stated interval to cover that until the creep term is modelled explicitly.
CREEP_REL_ALLOWANCE = 0.03


def _calibration_quantities(
    inputs: Sequence[PointInputs], ctx: LoadingContext
) -> dict[str, Quantity]:
    """Calibration slope (m/V), intercept (m) and tare (V) as named results, when available."""
    # frob:ticket 01M71XGHCQP7KZ6HEFPJ2KEMF8
    out: dict[str, Quantity] = {}
    cal = [i for i in inputs if isinstance(i, CalibrationInputs)]
    if len(cal) >= MIN_POINTS:
        fit = fit_calibration([c.volts for c in cal], [c.height for c in cal])
        if isinstance(fit, Ok):
            f = fit.danger_ok
            out["slope"] = _quantity(f.slope, "m/V")
            out["intercept"] = _quantity(f.intercept, "m")
    if ctx.tare_v is not None:
        tare = [i for i in inputs if isinstance(i, TareInputs)][-1]
        # frob:ticket 01M725CA43JK1ZDJKF8135RHT0
        # One tare model shared with the CSV export: pooled mean, standard error Sx/sqrt(N).
        blocks = [i for i in inputs if isinstance(i, TareInputs)]
        rep = tare_report([b.mean for b in blocks], [b.sd for b in blocks], [b.n for b in blocks])
        if isinstance(rep, Ok):
            out["tare"] = Quantity(
                value=rep.danger_ok.value, standard_uncertainty=rep.danger_ok.std_unc, unit="V"
            )
        else:  # blocks too small to pool: fall back to the last block's sd/sqrt(n)
            se = tare.sd / math.sqrt(tare.n) if tare.n >= 1 else tare.sd
            out["tare"] = Quantity(value=tare.mean, standard_uncertainty=se, unit="V")
    _log.debug("lctt calibration quantities: %s", sorted(out))
    return out


def _with_calibration(res: AnalysisResult, inputs: Sequence[PointInputs]) -> AnalysisResult:
    """Return `res` plus the calibration/tare quantities derived from `inputs`."""
    ctx = context_from_inputs(inputs)
    return res.model_copy(update={"values": {**res.values, **_calibration_quantities(inputs, ctx)}})


#: Two-specimen results that need both an elastic and a plastic run.
_TWO_SPECIMEN_NAMES = ("E", "r2", "yield_stress")


def _with_unavailable(res: AnalysisResult, reason: str) -> AnalysisResult:
    """Return `res` with the two-specimen results marked pending and `reason` as a note."""
    # frob:ticket 01M720GS24E4C7S5H9H1DPD95G
    have = tuple(n for n in _TWO_SPECIMEN_NAMES if n not in res.values)
    return res.model_copy(
        update={
            "pending": tuple(dict.fromkeys((*res.pending, *have))),
            "notes": (*res.notes, reason),
        }
    )


def _inflate_modulus_unc(
    value: float, unc: float, inputs: Sequence[PointInputs], ctx: LoadingContext
) -> float:
    """Add systematic terms (calibration slope, diameter, creep) to E's regression SE in quadrature.

    The OLS standard error alone ignores everything that scales the whole curve, which made
    the reported interval miss the truth most of the time.
    """
    # frob:ticket 01M71XGHCQP7KZ6HEFPJ2KEMF8
    rel2 = CREEP_REL_ALLOWANCE**2
    if ctx.diameter_m > 0:
        rel2 += (2.0 * ctx.u_diameter_m / ctx.diameter_m) ** 2
    cal = [i for i in inputs if isinstance(i, CalibrationInputs)]
    if len(cal) >= MIN_POINTS:
        fit = fit_calibration([c.volts for c in cal], [c.height for c in cal])
        if isinstance(fit, Ok) and fit.danger_ok.slope.value != 0:
            rel2 += (fit.danger_ok.slope.std_unc / abs(fit.danger_ok.slope.value)) ** 2
    total = math.sqrt(unc**2 + (value * value) * rel2)
    _log.info("lctt E uncertainty: regression %g -> %g with systematics", unc, total)
    return total


class LcttLab:
    """The LCTT lab: calibration, then an elastic (long) and a plastic (short) specimen run."""

    id = LabId("lctt")
    title = "Load-controlled creep/thermal test"
    models: tuple[type[BaseModel], ...] = (SpecimenSpec,)
    export_formats: tuple[ExportFormat, ...] = (CSV_FORMAT, FIGURE_FORMAT)

    def __init__(self, context: LoadingContext | None = None) -> None:
        """Hold the loading context (nominal geometry, no calibration unless given)."""
        self.context = context or LoadingContext()

    def steps(self) -> list[StepSpec]:
        """Return the ordered wizard steps, bound to calibration, elastic and plastic phases."""
        return lctt_steps()

    def recompute(self, points: tuple[CapturedPoint, ...]) -> Result[AnalysisResult, ComputeError]:
        """Pure: stress, strain and secant modulus of the last usable point; skips are logged."""
        usable = [p for p in points if p.volts is not None and p.load_kg is not None]
        _log.debug("lctt recompute: %d of %d points usable", len(usable), len(points))
        for p in points:
            if p not in usable:
                _log.info("lctt recompute: point %d skipped (volts/load_kg missing)", p.index)
        if not usable:
            return Err(
                ComputeError(code=ComputeCode.TOO_FEW_POINTS, detail="no point has volts and load")
            )
        ctx, last = self.context, usable[-1]
        dia = _meas(ctx.diameter_m, ctx.u_diameter_m, "m")
        mass = _meas(last.load_kg or 0.0, 0.0, "kg")
        hang = _meas(ctx.hanger_kg, 0.0, "kg")
        g = _meas(STANDARD_G, 0.0, "m/s^2")
        if dia is None or mass is None or hang is None or g is None:
            return Err(ComputeError(code=ComputeCode.NOT_FINITE, detail="invalid load inputs"))
        force, area = load_force(mass, hang, g), cross_area(dia)
        if isinstance(force, Err) or isinstance(area, Err):
            return Err(ComputeError(code=ComputeCode.DEGENERATE, detail="load propagation failed"))
        sig = stress(force.danger_ok, area.danger_ok)
        if isinstance(sig, Err):
            return Err(
                ComputeError(code=ComputeCode.DEGENERATE, detail="stress propagation failed")
            )
        values = {"stress": _quantity(sig.danger_ok, "Pa")}
        if ctx.slope_m_per_v is None or ctx.tare_v is None:
            _log.info("lctt recompute: no slope/tare in context; strain and modulus omitted")
            return Ok(AnalysisResult(values=values))
        slope = _meas(ctx.slope_m_per_v, 0.0, "m/V")
        volts = _meas(last.volts or 0.0, last.volts_sd or 0.0, "V")
        tare = _meas(ctx.tare_v, 0.0, "V")
        l0 = _meas(ctx.l0_m, 0.0, "m")
        if slope is None or volts is None or tare is None or l0 is None:
            return Err(ComputeError(code=ComputeCode.NOT_FINITE, detail="invalid strain inputs"))
        eps = strain(slope, volts, tare, l0)
        if isinstance(eps, Err):
            return Err(
                ComputeError(code=ComputeCode.DEGENERATE, detail="strain propagation failed")
            )
        values["strain"] = _quantity(eps.danger_ok, "1")
        if eps.danger_ok.value != 0.0:
            sec = secant_modulus(sig.danger_ok, eps.danger_ok)
            if isinstance(sec, Ok):
                values["secant_modulus"] = _quantity(sec.danger_ok, "Pa")
        _log.info("lctt recompute: %d values from point %d", len(values), last.index)
        return Ok(AnalysisResult(values=values))

    def analyze(
        self, points: tuple[CapturedPoint, ...], inputs: Sequence[PointInputs]
    ) -> Result[AnalysisResult, ComputeError]:
        """Pure: `recompute` under the context derived from `inputs`, plus E/yield for two runs.

        When both an elastic and a plastic run were captured, `combine_runs` adds `E`, `r2` and
        `yield_stress`; a combine failure is logged and the single-point values still return.
        """
        # frob:ticket 01M6WSH43VHA5WGRPQ20X1NQA9
        res = self._analyze(points, inputs)
        if res.is_err or any(isinstance(i, SpecimenInputs) for i in inputs):
            return res
        note = diameter_assumed_note()
        _log.warning("lctt analyze: %s", note)
        ok = res.danger_ok
        return Ok(ok.model_copy(update={"notes": (note, *ok.notes)}))

    def _analyze(
        self, points: tuple[CapturedPoint, ...], inputs: Sequence[PointInputs]
    ) -> Result[AnalysisResult, ComputeError]:
        """Analysis body of `analyze`, before the assumed-diameter note is added."""
        base = LcttLab(context_from_inputs(inputs)).recompute(points)
        if isinstance(base, Err):
            return base
        loads = [i for i in inputs if isinstance(i, LoadInputs)]
        by_role = {role: tuple(i for i in loads if i.phase == role.value) for role in SpecimenRole}
        missing = [r.value for r in SpecimenRole if not by_role[r]]
        if missing:
            return Ok(
                _with_unavailable(
                    _with_calibration(base.danger_ok, inputs),
                    f"yield_stress: needs a {' and a '.join(missing)} run (none captured yet)",
                )
            )
        shared = tuple(i for i in inputs if not isinstance(i, LoadInputs))
        combined = combine_runs(
            SpecimenRun(
                spec=SpecimenSpec(role=SpecimenRole.ELASTIC), inputs=by_role[SpecimenRole.ELASTIC]
            ),
            SpecimenRun(
                spec=SpecimenSpec(role=SpecimenRole.PLASTIC), inputs=by_role[SpecimenRole.PLASTIC]
            ),
            shared,
        )
        if isinstance(combined, Err):
            _log.warning("lctt analyze: combine_runs failed: %s", combined.danger_err)
            return Ok(
                _with_unavailable(
                    _with_calibration(base.danger_ok, inputs),
                    f"yield_stress: two-specimen fit failed ({combined.danger_err})",
                )
            )
        ctx = LcttLab(context_from_inputs(inputs)).context
        values = dict(base.danger_ok.values)
        values.update(_calibration_quantities(inputs, ctx))
        for sv in combined.danger_ok.values:
            r = sv.result
            unc = r.std_unc
            if r.name == "E":
                unc = _inflate_modulus_unc(r.value, unc, inputs, ctx)
            values[r.name] = Quantity(value=r.value, standard_uncertainty=unc, unit=r.unit)
        _log.info("lctt analyze: %d values incl. two-specimen results", len(values))
        return Ok(
            AnalysisResult(
                values=values, pending=combined.danger_ok.pending, notes=combined.danger_ok.notes
            )
        )

    def budgets(self) -> list[LabBudget]:
        """Return nominal stress and modulus budgets from the public uncertainty engine."""
        return nominal_budgets()
