"""Figure data behind the lctt calibration and stress-strain plots, as a JSON document."""

# frob:ticket 01M6WVADB5YKXAVC43CQNBQVJW

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.core.errors import ComputeCode, ComputeError
from sadi.labs.lctt.calibration import fit_calibration
from sadi.labs.lctt.export_csv import build_document
from sadi.labs.lctt.live import CalPoint, LiveEvent
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

# Document date is metadata only; a constant keeps the derivation pure.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_PA_PER_MPA = 1e6


class CalibrationFitData(BaseModel):
    """Fitted calibration line and its 95% confidence band over the sampled volts."""

    model_config = ConfigDict(frozen=True)

    slope_m_per_v: float
    intercept_m: float
    r2: float
    n: int
    band_volts: list[float]
    band_height_m: list[float]
    band_half_width_m: list[float]


class CalibrationData(BaseModel):
    """Calibration scatter (volts vs height in m); `fit` is None until 3 points exist."""

    model_config = ConfigDict(frozen=True)

    volts: list[float]
    height_m: list[float]
    fit: CalibrationFitData | None


class StressStrainData(BaseModel):
    """Stress-strain scatter in strain and MPa; excluded points are flagged, not dropped."""

    model_config = ConfigDict(frozen=True)

    point_ids: list[str]
    strain: list[float]
    stress_mpa: list[float]
    excluded: list[bool]
    # frob:ticket 01M72D3CTDED2MGDY721RSM8M4
    #: Per-point phase ("elastic", "plastic" or "" if unphased); same length as the rest.
    phase: list[str] = []


class FigureData(BaseModel):
    """Everything the calibration and stress-strain figures plot, for one session."""

    model_config = ConfigDict(frozen=True)

    calibration: CalibrationData
    stress_strain: StressStrainData


def calibration_data(events: Sequence[LiveEvent]) -> CalibrationData:
    """Build the calibration scatter and, with enough points, the fit line and band."""
    cals = [e for e in events if isinstance(e, CalPoint)]
    volts = [c.volts for c in cals]
    heights = [c.height for c in cals]
    fit = fit_calibration(volts, heights)
    if fit.is_err:
        _log.info("figure data: no calibration fit over %d points", len(cals))
        return CalibrationData(volts=volts, height_m=heights, fit=None)
    f = fit.danger_ok
    band = f.ci_band(sorted(volts))
    view = CalibrationFitData(
        slope_m_per_v=f.slope.value,
        intercept_m=f.intercept.value,
        r2=f.r2,
        n=f.n,
        band_volts=list(band.volts),
        band_height_m=list(band.height),
        band_half_width_m=list(band.half_width),
    )
    return CalibrationData(volts=volts, height_m=heights, fit=view)


def stress_strain_data(events: Sequence[LiveEvent]) -> StressStrainData:
    """Build the stress-strain scatter; empty until the specimen and tare are recorded."""
    doc = build_document(list(events), date=_EPOCH)
    if doc.is_err:
        _log.info("figure data: stress-strain not ready: %s", doc.danger_err.name)
        return StressStrainData(point_ids=[], strain=[], stress_mpa=[], excluded=[], phase=[])
    rows = doc.danger_ok.rows
    return StressStrainData(
        point_ids=[r.point_id for r in rows],
        strain=[r.strain for r in rows],
        stress_mpa=[r.stress_pa / _PA_PER_MPA for r in rows],
        excluded=[r.excluded for r in rows],
        phase=[r.phase for r in rows],
    )


def figure_data(events: Sequence[LiveEvent]) -> Result[FigureData, ComputeError]:
    """Derive both figures' series; refuse when the session holds no recorded inputs."""
    if not events:
        _log.warning("figure data export refused: no events")
        return Err(ComputeError(code=ComputeCode.TOO_FEW_POINTS, detail="no recorded inputs"))
    return Ok(
        FigureData(calibration=calibration_data(events), stress_strain=stress_strain_data(events))
    )
