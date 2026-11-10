"""Read-only REST route for the advisory next-weight suggestion and enough-data indicator."""

# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:ticket 01M72VM5TYFDN445BY0W9G68B1

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Query

from sadi.core.point_inputs import (
    PHASE_CALIBRATION,
    CalibrationInputs,
    LoadInputs,
    parse_inputs,
)
from sadi.design.models import (
    Candidate,
    ConfidenceIndicator,
    CurrentFit,
    DesignAdvice,
    DesignPhase,
    GpState,
    Obs,
    SelectorConfig,
    TargetSpec,
)
from sadi.design.selector import select_next
from sadi.labs.lctt.loading import SHORT_L0_M
from sadi.logging_setup import get_logger
from sadi.server.routes.problem import ApiProblem, ProblemError, unwrap
from sadi.server.schemas import PointView
from sadi.server.service import SessionService

_log = get_logger(__name__)

#: Safe load range (kg) and grid size for the load candidates; matches the guided-run default.
LOAD_MAX_KG = 5.0
N_CANDIDATES = 41
#: Default gauge-height range (m) for the LVDT calibration phase.
HEIGHT_MAX_M = 0.02
#: Fraction of the load range the elastic run may reach (keeps it below the expected yield load).
ELASTIC_MAX_FRAC = 0.6
#: Wizard point phases that feed each design phase (elastic and plastic are different specimens).
PHASES_FOR: dict[DesignPhase, frozenset[str]] = {
    DesignPhase.LVDT_CAL: frozenset({PHASE_CALIBRATION}),
    DesignPhase.ELASTIC: frozenset({"elastic"}),
    DesignPhase.YIELD: frozenset({"plastic"}),
}
#: Offset strain of the yield criterion (0.2 %).
OFFSET_STRAIN = 0.002
#: Minimum elastic points before a yield offset can be derived.
MIN_ELASTIC = 3


def offset_volts(views: list[PointView]) -> tuple[float | None, str]:
    """0.2 % offset in volts from the recorded calibration; (None, reason) when it is not derivable."""
    if len(design_obs(views, DesignPhase.ELASTIC)) < MIN_ELASTIC:
        return None, "no_elastic_fit"
    cal = design_obs(views, DesignPhase.LVDT_CAL)
    volts = np.array([o.y for o in cal])
    if len(cal) < 2 or float(np.ptp(volts)) <= 0.0:
        return None, "no_calibration"
    slope = float(np.polyfit(volts, [o.x for o in cal], 1)[0])
    if slope == 0.0 or not np.isfinite(slope):
        return None, "no_calibration"
    return OFFSET_STRAIN * SHORT_L0_M / abs(slope), ""


def _unavailable(phase: DesignPhase, n: int, target: TargetSpec, reason: str) -> DesignAdvice:
    """Advice with no suggestion and a collecting indicator that names why."""
    cfg = SelectorConfig()
    ind = ConfidenceIndicator(
        phase=phase, job_version=n, n=n, target=target,
        current=CurrentFit(half_width=None, value=None, dof=0.0), ratio=None,
        state=GpState.COLLECTING, consecutive_ok=0, patience=cfg.patience, reasons=(reason,),
    )
    return DesignAdvice(suggestion=None, indicator=ind)


def design_obs(views: list[PointView], phase: DesignPhase) -> list[Obs]:
    """Observations from active, settled (or human force-accepted) points of the phase's kind."""
    want = PHASES_FOR[phase]
    out: list[Obs] = []
    for p in sorted(views, key=lambda v: v.seq):
        if p.excluded or p.phase not in want or not (p.settled or p.forced_early):
            continue
        parsed = parse_inputs(p.phase, p.inputs)
        item = parsed.danger_ok if parsed.is_ok else None
        if isinstance(item, LoadInputs):
            out.append(Obs(x=item.mass_kg, y=item.volts, u=item.u_volts))
        elif isinstance(item, CalibrationInputs):
            out.append(Obs(x=item.height, y=item.volts))
        else:
            _log.warning("design: point %s unreadable; skipped", p.point_id)
    return out


def candidate_grid(hi: float, unit_id: str) -> list[Candidate]:
    """Evenly spaced candidates over [0, hi]."""
    return [
        Candidate(candidate_id=f"{unit_id}{i}", x=hi * i / (N_CANDIDATES - 1))
        for i in range(N_CANDIDATES)
    ]


def make_design_router(svc: SessionService) -> APIRouter:
    """Build the design router; GET only, so suggestions can never write session data."""
    r = APIRouter(prefix="/api")

    @r.get("/design/next-weight")
    def next_weight(
        phase: DesignPhase = DesignPhase.ELASTIC,
        target: float = Query(0.05, gt=0),
        offset: float | None = None,
    ) -> DesignAdvice:
        """Advisory next load (kg) or height (m) and the enough-data indicator; never acts."""
        views = unwrap(svc.points())
        obs = design_obs(views, phase)
        cal = phase is DesignPhase.LVDT_CAL
        if phase is DesignPhase.YIELD and offset is None:
            offset, why = offset_volts(views)
            if offset is None:
                _log.info("design: yield suggestion unavailable (%s)", why)
                return _unavailable(phase, len(obs), TargetSpec(half_width=target), why)
        top = HEIGHT_MAX_M if cal else LOAD_MAX_KG
        if phase is DesignPhase.ELASTIC:
            top = LOAD_MAX_KG * ELASTIC_MAX_FRAC
        cands = candidate_grid(top, "h" if cal else "m")
        res = select_next(
            phase,
            obs,
            cands,
            TargetSpec(half_width=target),
            SelectorConfig(offset_response=offset),
            unit="m" if cal else "kg",
            job_version=len(obs),
        )
        if res.is_err:
            err = res.danger_err
            _log.warning("design advice failed: %s", err.name)
            raise ProblemError(
                ApiProblem(
                    type=f"urn:sadi:error:design:{err.name}",
                    title=err.name,
                    status=422,
                    detail=err.value,
                    hint=err.value,
                )
            )
        return res.danger_ok

    return r
