"""REST routes for per-phase plot data (calibration, stress-strain), derived read-only."""

# frob:ticket 01M6WWN92GG11X653PP544SRDC

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result, propagate

from sadi.core.errors import ComputeCode, ComputeError
from sadi.labs.lctt.calibration import fit_calibration
from sadi.labs.lctt.export_csv import build_document
from sadi.labs.lctt.live import CalPoint, LiveEvent
from sadi.logging_setup import get_logger
from sadi.server.curve_source import session_events
from sadi.server.routes.problem import ApiProblem, from_sadi, unwrap
from sadi.server.service import SessionService

_log = get_logger(__name__)

# Document date is metadata only; a constant keeps the derivation pure.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_PA_PER_MPA = 1e6


class CalibrationFitView(BaseModel):
    """Fitted calibration line and its 95% confidence band over the sampled volts."""

    model_config = ConfigDict(frozen=True)

    slope_m_per_v: float
    intercept_m: float
    r2: float
    n: int
    band_volts: list[float]
    band_height_m: list[float]
    band_half_width_m: list[float]


class CalibrationPlot(BaseModel):
    """Calibration scatter (volts vs height in m); `fit` is None until 3 points exist."""

    model_config = ConfigDict(frozen=True)

    volts: list[float]
    height_m: list[float]
    fit: CalibrationFitView | None


class StressStrainPlot(BaseModel):
    """Stress-strain scatter in strain and MPa; excluded points are flagged, not dropped."""

    model_config = ConfigDict(frozen=True)

    point_ids: list[str]
    strain: list[float]
    stress_mpa: list[float]
    excluded: list[bool]


def calibration_plot(events: list[LiveEvent]) -> CalibrationPlot:
    """Build the calibration scatter and, with enough points, the fit line and band."""
    cals = [e for e in events if isinstance(e, CalPoint)]
    volts = [c.volts for c in cals]
    heights = [c.height for c in cals]
    fit = fit_calibration(volts, heights)
    if fit.is_err:
        _log.info("plots: no calibration fit over %d points: %s", len(cals), fit.danger_err.name)
        return CalibrationPlot(volts=volts, height_m=heights, fit=None)
    f = fit.danger_ok
    band = f.ci_band(sorted(volts))
    view = CalibrationFitView(
        slope_m_per_v=f.slope.value,
        intercept_m=f.intercept.value,
        r2=f.r2,
        n=f.n,
        band_volts=list(band.volts),
        band_height_m=list(band.height),
        band_half_width_m=list(band.half_width),
    )
    return CalibrationPlot(volts=volts, height_m=heights, fit=view)


def stress_strain_plot(events: list[LiveEvent]) -> StressStrainPlot:
    """Build the stress-strain scatter; empty until the specimen and tare are recorded."""
    doc = build_document(events, date=_EPOCH)
    if doc.is_err:
        _log.info("plots: stress-strain not ready: %s", doc.danger_err.name)
        return StressStrainPlot(point_ids=[], strain=[], stress_mpa=[], excluded=[])
    rows = doc.danger_ok.rows
    return StressStrainPlot(
        point_ids=[r.point_id for r in rows],
        strain=[r.strain for r in rows],
        stress_mpa=[r.stress_pa / _PA_PER_MPA for r in rows],
        excluded=[r.excluded for r in rows],
    )


@propagate
def _events(svc: SessionService) -> Result[list[LiveEvent], ApiProblem]:
    """Replay the open session into events, or the problem explaining why not."""
    path = svc.session_path().unwrap()
    events = session_events(path)
    if events.is_err:
        _log.error("plots: session replay failed: %s", events.danger_err)
        return Err(from_sadi(ComputeError(code=ComputeCode.DEGENERATE, detail="session replay")))
    return Ok(events.danger_ok)


def make_plots_router(svc: SessionService) -> APIRouter:
    """Build the plots router over `svc`; handlers are read-only projections of the event log."""
    r = APIRouter(prefix="/api/plots", tags=["plots"])

    @r.get("/calibration")
    def get_calibration() -> CalibrationPlot:
        """Calibration points with the fitted line and 95% band of the open session."""
        return calibration_plot(unwrap(_events(svc)))

    @r.get("/stress-strain")
    def get_stress_strain() -> StressStrainPlot:
        """Stress-strain points (strain, MPa) of the open session, excluded ones flagged."""
        return stress_strain_plot(unwrap(_events(svc)))

    return r
