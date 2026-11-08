"""Shared projections of session points onto core types for result and export routes."""

# frob:ticket 01M6WVADCSP63DBMYH3RNCXWTM

from __future__ import annotations

from sadi.core.models import CapturedPoint, SettleStatus, TimeWindow
from sadi.core.point_inputs import CalibrationInputs, LoadInputs, TareInputs, parse_inputs
from sadi.logging_setup import get_logger
from sadi.server.schemas import PointView

_log = get_logger(__name__)


def active_points(views: list[PointView]) -> list[PointView]:
    """Keep the active (non-excluded) points."""
    out = [p for p in views if not p.excluded]
    _log.debug("active_points: kept %d of %d", len(out), len(views))
    return out


def _raw_fields(p: PointView) -> tuple[float | None, float | None, float | None]:
    """Return (volts, volts_sd, load_kg) recorded for a point; None where its phase has none."""
    parsed = parse_inputs(p.phase, p.inputs)
    if parsed.is_err:
        _log.warning("point %s: raw inputs unreadable: %s", p.point_id, parsed.danger_err)
        return None, None, None
    item = parsed.danger_ok
    if isinstance(item, LoadInputs):
        return item.volts, item.volts_sd, item.mass_kg
    if isinstance(item, CalibrationInputs):
        return item.volts, None, None
    if isinstance(item, TareInputs):
        return item.mean, item.sd, None
    return None, None, None


def to_captured(views: list[PointView]) -> tuple[CapturedPoint, ...]:
    """Project active points onto the core `CapturedPoint`, carrying time, drift and status."""
    # frob:ticket 01M6WV1BEFANVC4BZ2S63NEPH5
    out: list[CapturedPoint] = []
    for i, p in enumerate(views):
        first = float(p.window.first_sample)
        volts, volts_sd, load_kg = _raw_fields(p)
        out.append(
            CapturedPoint(
                index=i,
                window=TimeWindow(start=first, end=max(first, float(p.window.last_sample))),
                t_since_load=max(0.0, p.t_since_load_s or 0.0),
                drift_rate=p.drift_rate or 0.0,
                status=SettleStatus.FORCED_EARLY if p.forced_early else SettleStatus.SETTLED,
                volts=volts,
                volts_sd=volts_sd,
                load_kg=load_kg,
            )
        )
    _log.debug("to_captured: projected %d points", len(out))
    return tuple(out)
