"""LabModule contract: what a lab plugin provides to the core shell and nothing more.

Core owns the device, session store, WAL, uncertainty engine, plotting contracts and wizard
state machine. A lab declares steps, analysis and export formats through this protocol and may
import only the core public API (enforced by tests/core/test_lab_boundary.py). Labs are
delivered by plugins (see sadi.plugins); discovery isolates import failures per plugin, but
there is no sandboxing and no hot reload, so enabled plugins are trusted in-process code.
"""

# frob:ticket 01M6W7R1G903HZ7V7JRCYC6ZT7

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import NewType, Protocol, assert_never, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field
from typani import Result

from sadi.core.errors import ComputeError
from sadi.core.models import CapturedPoint, Phase, Quantity, RunState
from sadi.logging_setup import get_logger
from sadi.uncertainty.budget import Budget

_log = get_logger(__name__)

LabId = NewType("LabId", str)
StepId = NewType("StepId", str)
ExportFormatId = NewType("ExportFormatId", str)

#: Deprecated entry-point group for bare lab packages; prefer the sadi.plugins group.
# frob:ticket 01M6WFYN8C6YH5D79CPEKSP69P
ENTRY_POINT_GROUP = "sadi.labs"


class CaptureKind(StrEnum):
    """What a wizard step captures; the core wizard dispatches on this."""

    NONE = "none"
    DEVICE_POINTS = "device_points"
    OPERATOR_INPUT = "operator_input"


def needs_device(kind: CaptureKind) -> bool:
    """Return True when a step of this capture kind reads the board (exhaustive over kinds)."""
    if kind is CaptureKind.DEVICE_POINTS:
        return True
    if kind is CaptureKind.NONE or kind is CaptureKind.OPERATOR_INPUT:
        return False
    assert_never(kind)


class _Frozen(BaseModel):
    """Base for immutable contract values; rejects unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)


class StepSpec(_Frozen):
    """One wizard step a lab declares: id, title, phase, capture kind, guidance and criterion."""

    id: StepId
    title: str = Field(min_length=1)
    phase: Phase
    capture: CaptureKind
    guidance: Callable[[RunState], str]
    #: Completion criterion: active (non-excluded) points needed before `complete`; skip ignores it.
    min_points: int = Field(default=0, ge=0)


class AnalysisResult(_Frozen):
    """Named quantities a lab's analysis produced (SI, with uncertainty)."""

    values: dict[str, Quantity]


#: Renders one export payload from a run and its analysis.
ExportWriter = Callable[[RunState, AnalysisResult], Result[bytes, ComputeError]]


class ExportFormat(_Frozen):
    """An export format a lab offers: id, human title, media type and writer."""

    id: ExportFormatId
    title: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    writer: ExportWriter


@runtime_checkable
class LabModule(Protocol):
    """The contract every lab implements; the core never reaches past it."""

    id: LabId
    title: str
    models: tuple[type[BaseModel], ...]
    export_formats: tuple[ExportFormat, ...]

    def steps(self) -> list[StepSpec]:
        """Return the ordered wizard steps of this lab."""
        ...

    def recompute(self, points: tuple[CapturedPoint, ...]) -> Result[AnalysisResult, ComputeError]:
        """Recompute the lab's results from the captured points."""
        ...


class LabBudget(_Frozen):
    """One result's uncertainty budget a lab offers: result id, label, budget and LaTeX."""

    result: str = Field(min_length=1)
    label: str = Field(min_length=1)
    budget: Budget
    latex: str


@runtime_checkable
class BudgetedLab(Protocol):
    """Optional lab hook: a lab that can state its results' uncertainty budgets."""

    def budgets(self) -> list[LabBudget]:
        """Return the budgets of the lab's results (empty when none are available)."""
        ...
