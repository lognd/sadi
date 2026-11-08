"""REST routes for per-phase plot data (calibration, stress-strain), derived read-only."""

# frob:ticket 01M6WWN92GG11X653PP544SRDC
# frob:ticket 01M6WXRTBQ3KWAB1JE0PBZRG82

from __future__ import annotations

from fastapi import APIRouter
from typani import Err, Ok, Result, propagate

from sadi.core.errors import ComputeCode, ComputeError
from sadi.labs.lctt.figure_data import (
    CalibrationData,
    CalibrationFitData,
    StressStrainData,
    calibration_data,
    stress_strain_data,
)
from sadi.labs.lctt.live import LiveEvent
from sadi.logging_setup import get_logger
from sadi.server.curve_source import session_events
from sadi.server.routes.problem import ApiProblem, from_sadi, unwrap
from sadi.server.service import SessionService

_log = get_logger(__name__)


class CalibrationFitView(CalibrationFitData):
    """Fitted calibration line and its 95% confidence band over the sampled volts."""


class CalibrationPlot(CalibrationData):
    """Calibration scatter (volts vs height in m); `fit` is None until 3 points exist."""

    fit: CalibrationFitView | None  # type: ignore[assignment]


class StressStrainPlot(StressStrainData):
    """Stress-strain scatter in strain and MPa; excluded points are flagged, not dropped."""


def calibration_plot(events: list[LiveEvent]) -> CalibrationPlot:
    """Adapt lctt `calibration_data` to the REST payload."""
    return CalibrationPlot.model_validate(calibration_data(events).model_dump())


def stress_strain_plot(events: list[LiveEvent]) -> StressStrainPlot:
    """Adapt lctt `stress_strain_data` to the REST payload."""
    return StressStrainPlot.model_validate(stress_strain_data(events).model_dump())


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
