"""LCTT lab: the seven-step two-specimen workflow and the combined E + yield results."""

# frob:ticket 01M6W7R3RXWS1WSH3TPXMK16Q2

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

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
from sadi.core.models import CapturedPoint, Phase, RunState
from sadi.core.point_inputs import (
    CalibrationInputs,
    LoadInputs,
    PointInputs,
    SpecimenInputs,
    TareInputs,
)
from sadi.core.results import ResultValue
from sadi.labs.lctt.budgets import nominal_budgets
from sadi.labs.lctt.clamp_check import ClampCheckConfig, setup_subcheck
from sadi.labs.lctt.export_csv import build_document, render_document
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
from sadi.labs.lctt.specimens import SpecimenRole, SpecimenSpec
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

#: Results taken from the long (elastic) specimen.
ELASTIC_RESULTS = ("E", "r2")
#: Results taken from the short (plastic) specimen.
PLASTIC_RESULTS = ("yield_stress",)


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


class LcttLab:
    """The LCTT lab: calibration, then an elastic (long) and a plastic (short) specimen run."""

    id = LabId("lctt")
    title = "Load-controlled creep/thermal test"
    models: tuple[type[BaseModel], ...] = (SpecimenSpec,)
    export_formats: tuple[ExportFormat, ...] = (CSV_FORMAT, FIGURE_FORMAT)

    def steps(self) -> list[StepSpec]:
        """Return the ordered wizard steps, bound to calibration, elastic and plastic phases."""
        return lctt_steps()

    def recompute(self, points: tuple[CapturedPoint, ...]) -> Result[AnalysisResult, ComputeError]:
        """Recompute core analysis from captured points; two-specimen results use combine_runs."""
        _log.debug("lctt recompute over %d points", len(points))
        return Ok(AnalysisResult(values={}))

    def budgets(self) -> list[LabBudget]:
        """Return nominal stress and modulus budgets from the public uncertainty engine."""
        return nominal_budgets()
