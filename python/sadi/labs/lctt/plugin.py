"""LCTT plugin entry: the register() factory that contributes the lctt LabModule."""

# frob:ticket 01M6WFZ1N70HDJJRZWRHWP4E7Y

from __future__ import annotations

from pydantic import BaseModel
from typani import Ok, Result

from sadi.core.errors import ComputeError
from sadi.core.lab import (
    AnalysisResult,
    CaptureKind,
    ExportFormat,
    LabId,
    LabModule,
    StepId,
    StepSpec,
)
from sadi.core.models import CapturedPoint, Phase, RunState
from sadi.logging_setup import get_logger

_log = get_logger(__name__)


def _guide(text: str):  # type: ignore[no-untyped-def]  # noqa: ANN202
    """Build a guidance hook returning fixed operator text."""

    def guidance(state: RunState) -> str:
        """Return the fixed guidance text for this step."""
        return text

    return guidance


class LcttLab:
    """The LCTT lab: calibration, elastic and plastic phases of a load-controlled test."""

    id = LabId("lctt")
    title = "Load-controlled creep/thermal test"
    models: tuple[type[BaseModel], ...] = ()
    export_formats: tuple[ExportFormat, ...] = ()

    def steps(self) -> list[StepSpec]:
        """Return the ordered wizard steps, one per guided-run phase."""
        return [
            StepSpec(
                id=StepId("calibrate"),
                title="LVDT calibration",
                phase=Phase.CALIBRATION,
                capture=CaptureKind.DEVICE_POINTS,
                guidance=_guide("Step the LVDT through known heights and capture each."),
            ),
            StepSpec(
                id=StepId("elastic"),
                title="Elastic loading",
                phase=Phase.ELASTIC,
                capture=CaptureKind.DEVICE_POINTS,
                guidance=_guide("Apply load increments and capture each settled point."),
            ),
            StepSpec(
                id=StepId("plastic"),
                title="Plastic hold",
                phase=Phase.PLASTIC,
                capture=CaptureKind.DEVICE_POINTS,
                guidance=_guide("Hold constant load and capture the creep response."),
            ),
        ]

    def recompute(self, points: tuple[CapturedPoint, ...]) -> Result[AnalysisResult, ComputeError]:
        """Recompute analysis from captured points (derived quantities are added per phase)."""
        _log.debug("lctt recompute over %d points", len(points))
        return Ok(AnalysisResult(values={}))


def register() -> LabModule:
    """Plugin entry point: return the lctt LabModule."""
    _log.info("lctt plugin register")
    return LcttLab()
