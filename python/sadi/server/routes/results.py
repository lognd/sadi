"""REST routes for live results, uncertainty budgets, guided-run guidance and device status."""

# frob:ticket 01M6WTCA1SET2XBYG05J73KJ11
# frob:ticket 01M6WVGZHZBY41K8M1BHYC1SYW
# frob:ticket 01M6WVADCSP63DBMYH3RNCXWTM

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, runtime_checkable

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.core.errors import ComputeCode
from sadi.core.lab import BudgetedLab, LabId, LabModule
from sadi.core.models import Quantity
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
from sadi.server.session_points import active_points, to_captured
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


#: Supplies the budgets of the open session's results (overrides the lab's own `budgets` hook).
BudgetSource = Callable[[], list[ResultBudget]]


def lab_budgets(svc: SessionService, labs: LabRegistry) -> list[ResultBudget]:
    """Budgets from the open session's lab when it implements `BudgetedLab`, else empty."""
    # frob:ticket 01M6WV1BBQYWGMK7W6KDD8P2N2
    info = svc.info()
    if info.is_err:
        return []
    got = labs.get(LabId(info.danger_ok.lab))
    if got.is_err or not isinstance(got.danger_ok, BudgetedLab):
        _log.debug("lab %s supplies no budgets", info.danger_ok.lab)
        return []
    out = [to_result_budget(b.result, b.label, b.budget, b.latex) for b in got.danger_ok.budgets()]
    _log.info("lab %s supplied %d budgets", info.danger_ok.lab, len(out))
    return out


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


class QuantityProvenance(BaseModel):
    """Where one reported quantity came from: its inputs, sample span and algorithm."""

    model_config = ConfigDict(frozen=True)

    name: str
    point_ids: tuple[str, ...]
    first_sample: int | None
    last_sample: int | None
    algorithm: str


class ResultsView(ResultSet):
    """`ResultSet` plus per-quantity provenance (which settle windows fed each value)."""

    provenance: tuple[QuantityProvenance, ...] = ()


def provenance_for(
    lab_id: str, names: list[str], active: list[PointView]
) -> tuple[QuantityProvenance, ...]:
    """Describe each named quantity: the active points and sample span behind it, and the lab."""
    firsts = [p.window.first_sample for p in active]
    lasts = [p.window.last_sample for p in active]
    ids = tuple(p.point_id for p in active)
    return tuple(
        QuantityProvenance(
            name=n,
            point_ids=ids,
            first_sample=min(firsts) if firsts else None,
            last_sample=max(lasts) if lasts else None,
            algorithm=f"{lab_id}.recompute",
        )
        for n in names
    )


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


def live_results(svc: SessionService, labs: LabRegistry) -> Result[ResultsView, ApiProblem]:
    """Recompute the open session's results and their provenance (the lctt recompute is a stub)."""
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
    active = active_points(pts.danger_ok)
    analysis = lab.recompute(to_captured(active))
    values = []
    notes: list[str] = []
    if analysis.is_err and analysis.danger_err.code == ComputeCode.TOO_FEW_POINTS:
        # Not enough captured input yet: an empty live panel with the reason, not a failure.
        _log.info("recompute waiting for inputs for lab %s: %s", lab.id, analysis.danger_err)
        notes.append(str(analysis.danger_err))
        quantities: dict[str, Quantity] = {}
    elif analysis.is_err:
        _log.warning("recompute failed for lab %s: %s", lab.id, analysis.danger_err)
        return Err(from_sadi(analysis.danger_err))
    else:
        quantities = analysis.danger_ok.values
    for name, q in quantities.items():
        made = make_result(name, q.value, q.standard_uncertainty, q.unit)
        if made.is_err:
            _log.warning("result %s not reportable: %s", name, made.danger_err)
            notes.append(f"{name}: {made.danger_err.description}")
        else:
            values.append(made.danger_ok)
    loads = [p for p in active if p.phase not in _NON_LOAD]
    _log.info("live results: %d values from %d points", len(values), len(active))
    prov = provenance_for(str(lab.id), [v.name for v in values], active)
    return Ok(
        ResultsView(n_points=len(loads), values=tuple(values), notes=tuple(notes), provenance=prov)
    )


def make_results_router(
    svc: SessionService,
    labs: LabRegistry,
    device: DeviceProbe | None = None,
    budgets: BudgetSource | None = None,
) -> APIRouter:
    """Build the results/guidance/device router over `svc`; handlers only delegate."""
    r = APIRouter(prefix="/api")

    @r.get("/results")
    def results() -> ResultsView:
        """Live recompute of the open session's results."""
        return unwrap(live_results(svc, labs))

    @r.get("/results/budgets")
    def result_budgets() -> list[ResultBudget]:
        """Per-result uncertainty budgets from the injected source, else the lab's own hook."""
        unwrap(svc.info())
        return budgets() if budgets is not None else lab_budgets(svc, labs)

    @r.get("/results/guidance")
    def guidance(
        phase: Phase = Phase.CALIBRATE,
        hold: HoldState = HoldState.READY,
        target: float | None = None,
    ) -> GuidanceState:
        """Guided-run advice for `phase` from the live results; never changes the phase."""
        rs = unwrap(live_results(svc, labs))
        views = active_points(unwrap(svc.points()))
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
