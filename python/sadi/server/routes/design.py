"""Read-only REST route for the advisory next-weight suggestion and enough-data indicator."""

# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4

from __future__ import annotations

from fastapi import APIRouter, Query

from sadi.core.point_inputs import (
    PHASE_CALIBRATION,
    PHASE_LOAD,
    CalibrationInputs,
    LoadInputs,
    parse_inputs,
)
from sadi.design.models import Candidate, DesignAdvice, DesignPhase, Obs, SelectorConfig, TargetSpec
from sadi.design.selector import select_next
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


def design_obs(views: list[PointView], phase: DesignPhase) -> list[Obs]:
    """Observations from active, settled (or human force-accepted) points of the phase's kind."""
    want = PHASE_CALIBRATION if phase is DesignPhase.LVDT_CAL else PHASE_LOAD
    out: list[Obs] = []
    for p in sorted(views, key=lambda v: v.seq):
        if p.excluded or p.phase != want or not (p.settled or p.forced_early):
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
        cands = candidate_grid(HEIGHT_MAX_M if cal else LOAD_MAX_KG, "h" if cal else "m")
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
