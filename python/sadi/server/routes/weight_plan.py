"""Weight-plan route: plan which inventory weights to hang, in order, with propagated uncertainty.

Stateless and read-only: it needs no open session or lab, so the operator can plan weights and
heights before anything is connected. The calibration slope defaults from the current session's
LVDT calibration points when there are any; otherwise the caller supplies it.
"""

# frob:ticket 01M72X7ZB936PEBXHRGX06FSAD

from __future__ import annotations

import math
from typing import Literal

import numpy as np
from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from typani import Err, Result

from sadi.design.models import DesignPhase, PlanConfig, PlanRequest, Weight, WeightPlan
from sadi.design.plan import PlanError, plan
from sadi.labs.lctt.loading import SHORT_L0_M
from sadi.labs.lctt.propagate import Hang as PropHang
from sadi.labs.lctt.propagate import PropagationInputs, propagate
from sadi.logging_setup import get_logger
from sadi.server.routes.design import design_obs
from sadi.server.routes.problem import ApiProblem, ProblemError
from sadi.server.service import SessionService
from sadi.uncertainty import Measured

_log = get_logger(__name__)

#: Default standard uncertainty (V) of one predicted LVDT reading.
DEFAULT_U_VOLTS = 0.001
#: Default wire diameter (m) shown to the operator (32 AWG copper); they should measure and replace it.
DEFAULT_DIAMETER_M = 0.000202


class WeightIn(BaseModel):
    """One entered weight: mass in kg, optional uncertainty, optional id (defaults to w1, w2...)."""

    model_config = ConfigDict(frozen=True)
    weight_id: str | None = None
    mass_kg: float = Field(gt=0)
    u_mass_kg: float = Field(default=0.0, ge=0)


class WeightPlanBody(BaseModel):
    """Operator inputs: weights, wire geometry and (optionally) the LVDT calibration slope."""

    model_config = ConfigDict(frozen=True)
    weights: list[WeightIn]
    diameter_m: float = Field(default=DEFAULT_DIAMETER_M, gt=0)
    u_diameter_m: float = Field(default=0.0, ge=0)
    length_m: float = Field(default=SHORT_L0_M, gt=0, description="gauge length L0")
    u_length_m: float = Field(default=0.0, ge=0)
    cal_slope_v_per_m: float | None = Field(
        default=None, description="LVDT volts per metre; defaults from the current calibration"
    )
    cal_offset_v: float = 0.0
    u_volts: float = Field(default=DEFAULT_U_VOLTS, ge=0)


class CalibrationDefaults(BaseModel):
    """The calibration slope the plan would use when none is entered, and where it came from."""

    model_config = ConfigDict(frozen=True)
    cal_slope_v_per_m: float | None
    source: Literal["session", "none"]
    explanation: str


class QuantityView(BaseModel):
    """A propagated value with standard uncertainty and its 95 % interval."""

    model_config = ConfigDict(frozen=True)
    name: str
    unit: str
    value: float
    std_unc: float
    low95: float
    high95: float


class PropagatedView(BaseModel):
    """Propagated uncertainty of the planned run: per-hang stress and strain, E and yield."""

    model_config = ConfigDict(frozen=True)
    stress: list[QuantityView]
    strain: list[QuantityView]
    modulus: QuantityView | None = None
    yield_stress: QuantityView | None = None
    notes: list[str] = []


class WeightPlanOut(BaseModel):
    """The plan, the slope that was used and the propagated uncertainty (when computable)."""

    model_config = ConfigDict(frozen=True)
    plan: WeightPlan
    cal_slope_v_per_m: float
    cal_source: Literal["entered", "session"]
    propagated: PropagatedView | None = None
    propagation_note: str = ""


def _problem(kind: str, title: str, detail: str, hint: str, status: int = 422) -> ProblemError:
    """A 4xx problem for the planner's refusals."""
    return ProblemError(
        ApiProblem(
            type=f"urn:sadi:error:weight_plan:{kind}",
            title=title,
            status=status,
            detail=detail,
            hint=hint,
        )
    )


def session_slope(svc: SessionService) -> float | None:
    """LVDT volts per metre fitted to the open session's calibration points; None if not derivable."""
    pts = svc.points()
    if pts.is_err:
        return None
    cal = design_obs(pts.danger_ok, DesignPhase.LVDT_CAL)
    heights = np.array([o.x for o in cal])
    if len(cal) < 2 or float(np.ptp(heights)) <= 0.0:
        return None
    slope = float(np.polyfit(heights, [o.y for o in cal], 1)[0])
    return slope if math.isfinite(slope) and slope != 0.0 else None


def _measured(value: float, unc: float, unit: str) -> Measured | None:
    """A Measured or None when the value is not usable."""
    made = Measured.create(value, unc, unit)
    return None if made.is_err else made.danger_ok


def _qview(q: object) -> QuantityView:
    """Compact view of a propagate Quantity."""
    return QuantityView(
        name=q.name,  # type: ignore[attr-defined]
        unit=q.unit,  # type: ignore[attr-defined]
        value=q.value,  # type: ignore[attr-defined]
        std_unc=q.std_unc,  # type: ignore[attr-defined]
        low95=q.low95,  # type: ignore[attr-defined]
        high95=q.high95,  # type: ignore[attr-defined]
    )


def _propagate(
    body: WeightPlanBody, weights: list[Weight], out: WeightPlan, slope: float
) -> tuple[PropagatedView | None, str]:
    """Propagate input uncertainty through the planned hangs; (None, why) when not possible."""
    if out.phase is not DesignPhase.ELASTIC or not out.hangs:
        return None, "Uncertainty is shown for the elastic plan only."
    index = {w.weight_id: i for i, w in enumerate(weights)}
    inv = [_measured(w.mass_kg, w.u_mass_kg, "kg") for w in weights]
    parts = [
        _measured(0.0, 0.0, "kg"),
        _measured(body.diameter_m, body.u_diameter_m, "m"),
        _measured(body.length_m, body.u_length_m, "m"),
        _measured(1.0 / slope, 0.0, "m/V"),
        _measured(body.cal_offset_v, 0.0, "V"),
    ]
    volts = [_measured(h.predicted_volts, body.u_volts, "V") for h in out.hangs]
    if any(m is None for m in [*inv, *parts, *volts]):
        return None, "Uncertainty could not be computed from these numbers."
    hangs = tuple(
        PropHang(weights=tuple(index[i] for i in h.weight_ids), voltage=v)  # type: ignore[arg-type]
        for h, v in zip(out.hangs, volts, strict=True)
    )
    res = propagate(
        PropagationInputs(
            inventory=tuple(inv),  # type: ignore[arg-type]
            hanger=parts[0],  # type: ignore[arg-type]
            diameter=parts[1],  # type: ignore[arg-type]
            l0=parts[2],  # type: ignore[arg-type]
            slope=parts[3],  # type: ignore[arg-type]
            tare=parts[4],  # type: ignore[arg-type]
            hangs=hangs,
        )
    )
    if res.is_err:
        _log.warning("weight-plan: propagation failed: %s", res.danger_err)
        return None, str(res.danger_err)
    r = res.danger_ok
    view = PropagatedView(
        stress=[_qview(q) for q in r.stress],
        strain=[_qview(q) for q in r.strain],
        modulus=_qview(r.modulus) if r.modulus is not None else None,
        yield_stress=_qview(r.yield_stress) if r.yield_stress is not None else None,
        notes=list(r.notes),
    )
    return view, ""


def _build_weights(body: WeightPlanBody) -> list[Weight]:
    """Weights with ids assigned (w1, w2, ...) where the operator gave none."""
    return [
        Weight(
            weight_id=w.weight_id or f"w{i + 1}",
            mass_kg=w.mass_kg,
            u_mass_kg=w.u_mass_kg,
        )
        for i, w in enumerate(body.weights)
    ]


def make_weight_plan_router(svc: SessionService) -> APIRouter:
    """Build the weight-plan router; reads the session only for the calibration default."""
    r = APIRouter(prefix="/api")

    @r.get("/weight-plan/defaults")
    def defaults() -> CalibrationDefaults:
        """The calibration slope used when none is entered, and where it comes from."""
        slope = session_slope(svc)
        if slope is None:
            return CalibrationDefaults(
                cal_slope_v_per_m=None,
                source="none",
                explanation=(
                    "No LVDT calibration yet. The slope is volts per metre of LVDT travel: "
                    "move the gauge to several known heights, read the volts, and take the "
                    "straight-line slope. Enter it, or run the calibration step first."
                ),
            )
        return CalibrationDefaults(
            cal_slope_v_per_m=slope,
            source="session",
            explanation="Fitted from this session's LVDT calibration points.",
        )

    @r.post("/weight-plan")
    def make_plan(body: WeightPlanBody) -> WeightPlanOut:
        """Ordered hangs with predicted volts and propagated uncertainty; advisory, writes nothing."""
        slope, source = body.cal_slope_v_per_m, "entered"
        if slope is None:
            slope, source = session_slope(svc), "session"
        if slope is None or not math.isfinite(slope) or slope == 0.0:
            raise _problem(
                "no_calibration",
                "no calibration slope",
                "No LVDT calibration slope was entered and none exists in the session.",
                "Enter the LVDT slope (volts per metre), or complete the calibration step first.",
            )
        weights = _build_weights(body)
        req = PlanRequest(
            weights=tuple(weights),
            diameter_m=body.diameter_m,
            u_diameter_m=body.u_diameter_m,
            length_m=body.length_m,
            u_length_m=body.u_length_m,
            cal_slope_v_per_m=slope,
            cal_offset_v=body.cal_offset_v,
            config=PlanConfig(),
        )
        res: Result[WeightPlan, PlanError] = plan(req)
        if isinstance(res, Err):
            err = res.unwrap_err()
            _log.info("weight-plan refused: %s", err)
            raise _problem("refused", "no plan", str(err), str(err))
        out = res.danger_ok
        view, note = _propagate(body, weights, out, slope)
        _log.info("weight-plan ok: %d hangs (%s)", len(out.hangs), source)
        return WeightPlanOut(
            plan=out,
            cal_slope_v_per_m=slope,
            cal_source="entered" if source == "entered" else "session",
            propagated=view,
            propagation_note=note,
        )

    return r
