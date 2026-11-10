"""Payloads and error codes of the sequential-design selector (docs/design/gp-selector.md)."""

# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from sadi.labs.lctt.gp_suggester import GpState

__all__ = [
    "AltCandidate",
    "Candidate",
    "ConfidenceIndicator",
    "Criterion",
    "CurrentFit",
    "DesignAdvice",
    "DesignPhase",
    "GpState",
    "NextSuggestion",
    "Obs",
    "SelectorConfig",
    "SelectorError",
    "TargetSpec",
]

SCHEMA_VERSION = 1


class DesignPhase(StrEnum):
    """Which model the design uses: LVDT calibration, elastic fit or yield GP."""

    LVDT_CAL = "lvdt_cal"
    ELASTIC = "elastic"
    YIELD = "yield"


class Criterion(StrEnum):
    """Acquisition criterion; `target` is c-optimal (expected shrink of the target interval)."""

    TARGET = "target"
    D_OPT = "d_opt"
    A_OPT = "a_opt"


class SelectorError(StrEnum):
    """Why the selector could not advise; the value is the plain-language hint."""

    NoCandidates = "There are no candidate loads to choose from"
    SingularPosterior = "The model could not be fitted to these points (degenerate data)"
    NonFinite = "A measurement or candidate is not a finite number"
    BudgetExceeded = "The suggestion took longer than its time budget"
    InvalidTarget = "The target half-width must be a finite number above zero"


class Candidate(BaseModel):
    """One allowed next setting (a load in kg, or a gauge height in m) with its own uncertainty."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    x: float
    u_x: float = 0.0


class Obs(BaseModel):
    """One settled, confirmed observation: design variable x, response y, uncertainty u."""

    model_config = ConfigDict(frozen=True)

    x: float
    y: float
    u: float = 0.0


class TargetSpec(BaseModel):
    """User target half-width of the 95 % interval; relative to the estimate unless stated."""

    model_config = ConfigDict(frozen=True)

    half_width: float
    unit: str = ""
    relative: bool = True


class CurrentFit(BaseModel):
    """Current estimate of the target quantity; `half_width` is None while it cannot be formed."""

    model_config = ConfigDict(frozen=True)

    half_width: float | None
    value: float | None
    dof: float


class SelectorConfig(BaseModel):
    """Tunable selector settings (spec section 2 and 4 defaults)."""

    model_config = ConfigDict(frozen=True)

    patience: int = Field(default=2, ge=1)
    margin: float = Field(default=0.9, gt=0, le=1)
    eps: float = Field(default=0.02, ge=0)
    n_min_linear: int = Field(default=3, ge=3)
    n_min_yield: int = Field(default=5, ge=4)
    max_gp_points: int = Field(default=60, ge=8)
    max_window: int = Field(default=64, ge=4)
    budget_ms: float = 150.0
    criterion: Criterion = Criterion.TARGET
    #: 0.2 % offset expressed in response units (yield phase); required for the yield GP.
    offset_response: float | None = None


#: Stable machine codes naming why an indicator has no usable fit (the UI keys on these).
ReasonCode = Literal[
    "cold_start",
    "singular",
    "no_offset",
    "yield_not_reached",
    "departure_from_linear",
    "diminishing_returns",
    "no_elastic_fit",
    "no_calibration",
]


class ConfidenceIndicator(BaseModel):
    """The "confidence is enough" payload (advisory; the user always decides)."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    phase: DesignPhase
    job_version: int
    n: int
    target: TargetSpec
    current: CurrentFit
    ratio: float | None
    state: GpState
    consecutive_ok: int
    patience: int
    advisory: Literal[True] = True
    reasons: tuple[ReasonCode, ...] = ()


class AltCandidate(BaseModel):
    """A runner-up candidate with its expected gain."""

    model_config = ConfigDict(frozen=True)

    candidate_id: str
    x: float
    expected_gain: float


class NextSuggestion(BaseModel):
    """Recommended next candidate with the expected gain; never acts on the machine."""

    model_config = ConfigDict(frozen=True)

    schema_version: int = SCHEMA_VERSION
    phase: DesignPhase
    job_version: int
    candidate_id: str
    x: float
    unit: str
    expected_gain: float
    expected_half_width: float | None
    alternatives: tuple[AltCandidate, ...] = ()
    criterion: Criterion = Criterion.TARGET
    elapsed_ms: float = 0.0
    budget_exceeded: bool = False
    advisory: Literal[True] = True
    #: One plain-language sentence saying why this value was chosen (for students).
    why: str = ""


class DesignAdvice(BaseModel):
    """REST payload: the suggestion (None when there is nothing to suggest) plus the indicator."""

    model_config = ConfigDict(frozen=True)

    suggestion: NextSuggestion | None
    indicator: ConfidenceIndicator
    advisory: Literal[True] = True
