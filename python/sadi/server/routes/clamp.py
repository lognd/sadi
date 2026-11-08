"""REST route for the Setup-step clamp check: progress and verdict over the captured cycles."""

# frob:ticket 01M6XA21KQE5WEXAN39683H4S9

from __future__ import annotations

from fastapi import APIRouter

from sadi.core.point_inputs import PHASE_SETUP, ClampInputs, parse_inputs
from sadi.labs.lctt.clamp_check import ClampStatus, clamp_status
from sadi.logging_setup import get_logger
from sadi.server.routes.problem import unwrap
from sadi.server.schemas import PointView
from sadi.server.service import SessionService

_log = get_logger(__name__)


def recorded_cycles(views: list[PointView]) -> list[tuple[float, float, int]]:
    """Active setup points as (zero_before, zero_after, slip_events); unreadable ones are logged."""
    out: list[tuple[float, float, int]] = []
    for p in views:
        if p.excluded or p.phase != PHASE_SETUP:
            continue
        parsed = parse_inputs(p.phase, p.inputs)
        item = parsed.danger_ok if parsed.is_ok else None
        if isinstance(item, ClampInputs):
            out.append((item.zero_before, item.zero_after, item.slip_events))
        else:
            _log.warning("setup point %s unreadable; skipped", p.point_id)
    return out


def make_clamp_router(svc: SessionService) -> APIRouter:
    """Build the clamp-check router; read-only, captures go through POST /api/session/points."""
    r = APIRouter(prefix="/api")

    @r.get("/session/clamp-check")
    def clamp_check() -> ClampStatus:
        """Procedure, recorded cycles and the clamp-check verdict."""
        return clamp_status(recorded_cycles(unwrap(svc.points())))

    return r
