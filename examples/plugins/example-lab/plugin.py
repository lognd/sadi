"""Example lab (plugin demo): one capture step whose result is the mean applied load.

WHY: shows the smallest complete plugin using only the public core API (sadi.core,
sadi.logging_setup, typani). WHAT: ``make_lab`` is the entrypoint named in
``sadi_plugin.toml``; copy this file to start a real lab.
"""

from __future__ import annotations

import math

from typani import Err, Ok, Result

from sadi.core.errors import ComputeCode, ComputeError
from sadi.core.lab import AnalysisResult, CaptureKind, LabId, LabModule, StepId, StepSpec
from sadi.core.models import CapturedPoint, Phase, Quantity, RunState
from sadi.logging_setup import get_logger

_log = get_logger(__name__)


def _guidance(state: RunState) -> str:
    """Tell the student what to do at the measure step."""
    return "Hang the load, wait for the reading to settle, then capture."


class ExampleLab:
    """Example lab (plugin demo): one capture step; the result is the mean applied load."""

    id = LabId("example-lab")
    title = "Example lab (plugin demo)"
    models = ()
    export_formats = ()

    def steps(self) -> list[StepSpec]:
        """Return the single measure step."""
        return [
            StepSpec(
                id=StepId("measure"),
                title="Measure",
                phase=Phase.ELASTIC,
                capture=CaptureKind.DEVICE_POINTS,
                guidance=_guidance,
                min_points=1,
            )
        ]

    def recompute(self, points: tuple[CapturedPoint, ...]) -> Result[AnalysisResult, ComputeError]:
        """Mean applied load in kg with its standard error; Err when no loads exist."""
        loads = [p.load_kg for p in points if p.load_kg is not None]
        if not loads:
            _log.warning("example-lab recompute: no loads in %d points", len(points))
            return Err(ComputeError(code=ComputeCode.TOO_FEW_POINTS, detail="no loads"))
        n = len(loads)
        mean = sum(loads) / n
        sem = 0.0
        if n > 1:
            sem = math.sqrt(sum((x - mean) ** 2 for x in loads) / (n - 1) / n)
        _log.info("example-lab recompute: n=%d mean=%.6g", n, mean)
        return Ok(
            AnalysisResult(
                values={"mean_load": Quantity(value=mean, standard_uncertainty=sem, unit="kg")}
            )
        )


def make_lab() -> LabModule:
    """Plugin entrypoint: return the example LabModule."""
    _log.info("example-lab plugin make_lab")
    return ExampleLab()
