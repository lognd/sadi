"""Shared projections of session points onto core types for result and export routes."""

# frob:ticket 01M6WVADCSP63DBMYH3RNCXWTM

from __future__ import annotations

from sadi.core.models import CapturedPoint, SettleStatus, TimeWindow
from sadi.logging_setup import get_logger
from sadi.server.schemas import PointView

_log = get_logger(__name__)


def active_points(views: list[PointView]) -> list[PointView]:
    """Keep the active (non-excluded) points."""
    out = [p for p in views if not p.excluded]
    _log.debug("active_points: kept %d of %d", len(out), len(views))
    return out


def to_captured(views: list[PointView]) -> tuple[CapturedPoint, ...]:
    """Project active points onto the core `CapturedPoint`, carrying time, drift and status."""
    # frob:ticket 01M6WV1BEFANVC4BZ2S63NEPH5
    out: list[CapturedPoint] = []
    for i, p in enumerate(views):
        first = float(p.window.first_sample)
        out.append(
            CapturedPoint(
                index=i,
                window=TimeWindow(start=first, end=max(first, float(p.window.last_sample))),
                t_since_load=max(0.0, p.t_since_load_s or 0.0),
                drift_rate=p.drift_rate or 0.0,
                status=SettleStatus.FORCED_EARLY if p.forced_early else SettleStatus.SETTLED,
            )
        )
    _log.debug("to_captured: projected %d points", len(out))
    return tuple(out)
