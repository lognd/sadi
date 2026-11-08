"""REST routes for live results, uncertainty budgets, guided-run guidance and device status."""

# frob:ticket 01M6WTCA1SET2XBYG05J73KJ11

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.core.lab import LabId, LabModule
from sadi.core.models import CapturedPoint, SettleStatus, TimeWindow
from sadi.core.point_inputs import PHASE_CALIBRATION, PHASE_SPECIMEN, PHASE_TARE
from sadi.core.registry import LabRegistry
from sadi.core.results import ResultSet, make_result
from sadi.labs.lctt.guidance import (
    GuidanceConfig,
    GuidanceError,
    GuidanceInput,
    GuidanceState,
    HoldState,
    Phase,
    guide,
)
from sadi.logging_setup import get_logger
from sadi.server.routes.problem import ApiProblem, from_sadi, not_found, unwrap
from sadi.server.schemas import PointView
from sadi.server.service import SessionService
from sadi.uncertainty.budget import Budget, BudgetRow

_log = get_logger(__name__)

#: Phases whose points are setup inputs, not load points.
_NON_LOAD = frozenset({PHASE_CALIBRATION, PHASE_TARE, PHASE_SPECIMEN})


class ResultBudget(BaseModel):
    """Ranked budget for one result plus its LaTeX derivation (mirrors web budget/types.ts)."""

    model_config = ConfigDict(frozen=True)

    result: str
    label: str
    total_variance: float
    total_std_unc: float
    dominant: BudgetRow | None
    rows: tuple[BudgetRow, ...]
    latex: str


def to_result_budget(result: str, label: str, budget: Budget, latex: str) -> ResultBudget:
    """Wrap a `Budget` from `Uncertain.budget` (and its `Uncertain.latex`) for the wire."""
    return ResultBudget(
        result=result,
        label=label,
        total_variance=budget.total_variance,
        total_std_unc=budget.total_std_unc,
        dominant=budget.dominant,
        rows=budget.rows,
        latex=latex,
    )


#: Supplies the budgets of the open session's results (a lab hook; none exist yet).
BudgetSource = Callable[[], list[ResultBudget]]


@runtime_checkable
class DeviceProbe(Protocol):
    """What the route needs of a device (`DeviceService` fits); keeps the native module optional."""

    @property
    def status(self) -> str:
        """Coarse state: connected, simulated or error."""
        ...

    @property
    def fault(self) -> object | None:
        """The error that stopped the reader, if any."""
        ...


class DeviceView(BaseModel):
    """Device state for the header: coarse status, whether a service exists, and any fault."""

    status: str
    attached: bool
    fault: str | None = None
    hint: str = ""


def _points_for(views: list[PointView]) -> list[PointView]:
    """Keep the active (non-excluded) points."""
    return [p for p in views if not p.excluded]


def _captured(views: list[PointView]) -> tuple[CapturedPoint, ...]:
    """Project active points onto the core `CapturedPoint` (time fields are not on the wire)."""
    out: list[CapturedPoint] = []
    for i, p in enumerate(views):
        first = float(p.window.first_sample)
        out.append(
            CapturedPoint(
                index=i,
                window=TimeWindow(start=first, end=max(first, float(p.window.last_sample))),
                t_since_load=0.0,
                drift_rate=0.0,
                status=SettleStatus.SETTLED,
            )
        )
    return tuple(out)


def _guidance_problem(err: ErrorSet) -> ApiProblem:
    """Map a GuidanceError member to a problem; its description is the hint."""
    bad_input = err in (GuidanceError.BadTarget, GuidanceError.BadRange)
    code = err.name.lower()
    return ApiProblem(
        type=f"urn:sadi:error:guidance:{code}",
        title=code,
        status=422 if bad_input else 500,
        detail=err.description,
        hint=err.description,
    )


def live_results(svc: SessionService, labs: LabRegistry) -> Result[ResultSet, ApiProblem]:
    """Recompute the open session's results through its lab (the lctt recompute is a stub)."""
    info = svc.info()
    pts = svc.points()
    if info.is_err or pts.is_err:
        return Err(info.danger_err if info.is_err else pts.danger_err)
    lab: LabModule | None = None
    got = labs.get(LabId(info.danger_ok.lab))
    if got.is_ok:
        lab = got.danger_ok
    if lab is None:
        return Err(
            not_found(info.danger_ok.lab, "Register the session's lab or resume with another.")
        )
    active = _points_for(pts.danger_ok)
    analysis = lab.recompute(_captured(active))
    if analysis.is_err:
        _log.warning("recompute failed for lab %s: %s", lab.id, analysis.danger_err)
        return Err(from_sadi(analysis.danger_err))
    values = []
    notes: list[str] = []
    for name, q in analysis.danger_ok.values.items():
        made = make_result(name, q.value, q.standard_uncertainty, q.unit)
        if made.is_err:
            _log.warning("result %s not reportable: %s", name, made.danger_err)
            notes.append(f"{name}: {made.danger_err.description}")
        else:
            values.append(made.danger_ok)
    loads = [p for p in active if p.phase not in _NON_LOAD]
    _log.info("live results: %d values from %d points", len(values), len(active))
    return Ok(ResultSet(n_points=len(loads), values=tuple(values), notes=tuple(notes)))


def make_results_router(
    svc: SessionService,
    labs: LabRegistry,
    device: DeviceProbe | None = None,
    budgets: BudgetSource | None = None,
) -> APIRouter:
    """Build the results/guidance/device router over `svc`; handlers only delegate."""
    r = APIRouter(prefix="/api")

    @r.get("/results")
    def results() -> ResultSet:
        """Live recompute of the open session's results."""
        return unwrap(live_results(svc, labs))

    @r.get("/results/budgets")
    def result_budgets() -> list[ResultBudget]:
        """Per-result uncertainty budgets; empty until the lab supplies a budget source."""
        unwrap(svc.info())
        return budgets() if budgets is not None else []

    @r.get("/results/guidance")
    def guidance(
        phase: Phase = Phase.CALIBRATE,
        hold: HoldState = HoldState.READY,
        target: float | None = None,
    ) -> GuidanceState:
        """Guided-run advice for `phase` from the live results; never changes the phase."""
        rs = unwrap(live_results(svc, labs))
        views = _points_for(unwrap(svc.points()))
        n_cal = sum(1 for p in views if p.phase == PHASE_CALIBRATION)
        cfg = GuidanceConfig() if target is None else GuidanceConfig(target=target)
        got = guide(phase, GuidanceInput(results=rs, n_cal_points=n_cal, hold=hold), cfg)
        if got.is_err:
            raise_problem = _guidance_problem(got.danger_err)
            _log.warning("guidance refused: %s", raise_problem.type)
            return unwrap(Err(raise_problem))
        return got.danger_ok

    @r.get("/device/status")
    def device_status() -> DeviceView:
        """Device status; attached=false (status error) when no device service is configured."""
        if device is None:
            return DeviceView(
                status="error",
                attached=False,
                hint="No device service is configured; start the server with a device source.",
            )
        fault = device.fault
        return DeviceView(
            status=device.status,
            attached=True,
            fault=None if fault is None else repr(fault)[:300],
            hint=getattr(fault, "hint", "") if fault is not None else "",
        )

    return r
