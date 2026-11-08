"""Pydantic domain models: quantities, specimen, captured points and run state.

All numeric fields are SI internally (m, kg, N, Pa, V, s); unit conversion happens
only at display time (see the formatter), never in these models.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

#: SI unit symbols accepted on a Quantity ("1" is dimensionless).
SI_UNITS: frozenset[str] = frozenset(
    {"1", "m", "kg", "s", "N", "Pa", "V", "m/V", "m^2", "kg*m/s^2", "1/s", "V/s", "m/s"}
)

Finite = Annotated[float, Field(allow_inf_nan=False)]
NonNeg = Annotated[float, Field(ge=0.0, allow_inf_nan=False)]


class _Frozen(BaseModel):
    """Base for immutable value models; rejects unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Quantity(_Frozen):
    """A measured value with its 95 % standard uncertainty, in an SI unit."""

    value: Finite
    standard_uncertainty: NonNeg = 0.0
    unit: str = "1"

    @model_validator(mode="after")
    def _check_unit(self) -> Quantity:
        """Reject non-SI unit symbols so conversion stays a display concern."""
        if self.unit not in SI_UNITS:
            _log.warning("rejected non-SI unit %r", self.unit)
            msg = f"unit {self.unit!r} is not an SI unit symbol"
            raise ValueError(msg)
        return self


class Specimen(_Frozen):
    """The wire under test: initial length L0 and diameter d, both in m."""

    id: str = Field(min_length=1)
    l0: Quantity
    diameter: Quantity
    description: str = ""

    @model_validator(mode="after")
    def _si_units(self) -> Specimen:
        """Require metre units and positive geometry."""
        for name, q in (("l0", self.l0), ("diameter", self.diameter)):
            if q.unit != "m" or q.value <= 0.0:
                msg = f"{name} must be a positive length in m"
                raise ValueError(msg)
        return self

    @property
    def area(self) -> Quantity:
        """Cross-section A = pi d^2 / 4 in m^2 with first-order uncertainty."""
        d, u = self.diameter.value, self.diameter.standard_uncertainty
        return Quantity(
            value=math.pi * d * d / 4.0,
            standard_uncertainty=math.pi * d * u / 2.0,
            unit="m^2",
        )


class Phase(StrEnum):
    """Guided-run phase."""

    # frob:ticket 01M6WJ8R4E0K2Z5K5KZJTJA6QM
    SETUP = "setup"
    CALIBRATION = "calibration"
    TARE = "tare"
    ELASTIC = "elastic"
    PLASTIC = "plastic"
    RESULTS = "results"
    EXPORT = "export"


class SettleStatus(StrEnum):
    """Whether a point was captured after settling or forced early."""

    SETTLED = "settled"
    FORCED_EARLY = "forced_early"


class TimeWindow(_Frozen):
    """Averaging window in seconds since run start; end >= start."""

    start: NonNeg
    end: NonNeg

    @model_validator(mode="after")
    def _ordered(self) -> TimeWindow:
        """Require end >= start."""
        if self.end < self.start:
            msg = "window end precedes start"
            raise ValueError(msg)
        return self


class PointEdit(_Frozen):
    """One re-edit of a captured point: which field changed, from what, to what."""

    field: str = Field(min_length=1)
    old: str
    new: str
    at: NonNeg


class CapturedPoint(_Frozen):
    """A captured (settled or forced-early) point with its provenance and edit history."""

    index: int = Field(ge=0)
    window: TimeWindow
    t_since_load: NonNeg
    drift_rate: Finite
    status: SettleStatus
    edits: tuple[PointEdit, ...] = ()
    # frob:ticket 01M6WH4Q5S0YYD0S8YW9T1EX41
    volts: Finite | None = None  # block-mean raw volts of the window; None for old data
    volts_sd: NonNeg | None = None  # per-sample sd of the raw volts; None when not recorded
    load_kg: NonNeg | None = None  # total hanging mass in kg; None for old data

    @property
    def settled(self) -> bool:
        """True when the point was captured after the drift criterion was met."""
        return self.status is SettleStatus.SETTLED

    @property
    def forced_early(self) -> bool:
        """True when the operator forced capture before settling."""
        return self.status is SettleStatus.FORCED_EARLY


class RunState(_Frozen):
    """Snapshot of a guided run: phase, specimen, tare and captured points."""

    session_id: str = Field(min_length=1)
    phase: Phase = Phase.CALIBRATION
    specimen: Specimen | None = None
    tare: Quantity | None = None
    points: tuple[CapturedPoint, ...] = ()
    # frob:ticket 01M6WVADB5YKXAVC43CQNBQVJW
    #: Lab-defined raw session events (opaque to the core) for writers that re-derive results.
    events: tuple[BaseModel, ...] = ()

    def advance(self, phase: Phase) -> RunState:
        """Return a copy moved to `phase`."""
        _log.info("run %s: phase %s -> %s", self.session_id, self.phase, phase)
        return self.model_copy(update={"phase": phase})

    def with_point(self, point: CapturedPoint) -> RunState:
        """Return a copy with `point` appended."""
        _log.info("run %s: captured point %d (%s)", self.session_id, point.index, point.status)
        return self.model_copy(update={"points": (*self.points, point)})
