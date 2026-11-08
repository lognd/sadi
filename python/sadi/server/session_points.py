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
    _log.debug("to_captured: projected %d points", len(out))
    return tuple(out)
