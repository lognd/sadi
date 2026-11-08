"""Single owner of the live run's guided phase, recorded append-only as MARKER records."""

# frob:ticket 01M6XAKF5AK7FCJNBHPM62NYRS

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.labs.lctt.guidance import Phase
from sadi.logging_setup import get_logger
from sadi.store.events import MarkerEntry, marker_record
from sadi.store.records import MarkerV1, NewRecord

_log = get_logger(__name__)

#: MARKER kind that carries a run-phase transition; `label` is the Phase value.
MARK_RUN_PHASE: Final = "run.phase"

#: The only legal order of run phases; a transition moves exactly one step forward.
PHASE_ORDER: Final[tuple[Phase, ...]] = (Phase.CALIBRATE, Phase.ELASTIC, Phase.PLASTIC)


class PhaseRefusal(BaseModel):
    """Why a phase transition was refused (the log is left untouched)."""

    model_config = ConfigDict(frozen=True)

    current: Phase | None
    requested: Phase
    reason: str


def next_allowed(current: Phase | None) -> Phase | None:
    """The one phase a run in `current` may enter next (None current -> first phase)."""
    if current is None:
        return PHASE_ORDER[0]
    idx = PHASE_ORDER.index(current)
    return PHASE_ORDER[idx + 1] if idx + 1 < len(PHASE_ORDER) else None


def check_transition(current: Phase | None, requested: Phase) -> Result[Phase, PhaseRefusal]:
    """Validate moving from `current` to `requested`: exactly the next phase, never back."""
    allowed = next_allowed(current)
    if allowed is None:
        return Err(PhaseRefusal(current=current, requested=requested, reason="run already ended"))
    if requested != allowed:
        return Err(
            PhaseRefusal(
                current=current,
                requested=requested,
                reason=f"next phase must be {allowed.value}",
            )
        )
    return Ok(requested)


def phase_record(phase: Phase) -> NewRecord:
    """The MARKER WAL record that records entry into `phase`."""
    return marker_record(MarkerV1(kind=MARK_RUN_PHASE, label=phase.value))


def fold_phase(markers: Iterable[MarkerEntry]) -> Phase | None:
    """Current recorded phase, or None when none was recorded (old sessions).

    Markers that are not valid transitions are skipped (logged), so a damaged or hand-made
    log can never move the phase out of order.
    """
    current: Phase | None = None
    for entry in markers:
        if entry.marker.kind != MARK_RUN_PHASE:
            continue
        try:
            requested = Phase(entry.marker.label)
        except ValueError:
            _log.warning("seq %d: unknown run phase %r ignored", entry.seq, entry.marker.label)
            continue
        ok = check_transition(current, requested)
        if ok.is_err:
            _log.warning("seq %d: run phase marker ignored: %s", entry.seq, ok.danger_err.reason)
            continue
        current = requested
    return current
