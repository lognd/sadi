"""Error taxonomy: typed values used as the E in typani Result[T, E], each with a user hint."""

from __future__ import annotations

from enum import StrEnum
from typing import ClassVar

from pydantic import BaseModel, ConfigDict

from sadi.logging_setup import get_logger

_log = get_logger(__name__)


class ErrorFamily(StrEnum):
    """Top-level error family; maps one-to-one to a problem+json `type` segment."""

    DEVICE = "device"
    INPUT = "input"
    STORE = "store"
    COMPUTE = "compute"
    JOB = "job"


class DeviceCode(StrEnum):
    """Failure codes for the SADI board and its transport."""

    NOT_FOUND = "not_found"
    DISCONNECTED = "disconnected"
    TIMEOUT = "timeout"
    PROTOCOL = "protocol"
    SATURATED = "saturated"


class InputCode(StrEnum):
    """Failure codes for user-supplied or model-level input."""

    OUT_OF_RANGE = "out_of_range"
    MISSING = "missing"
    DUPLICATE = "duplicate"
    UNKNOWN_ID = "unknown_id"
    BAD_UNIT = "bad_unit"


# frob:ticket 01M6WBKXD1562WNR2FQS9RXHNM
class StoreCode(StrEnum):
    """Failure codes for durable storage (WAL, events, snapshots)."""

    IO = "io"
    CORRUPT = "corrupt"
    LOCKED = "locked"
    VERSION = "version"
    BACKPRESSURE = "backpressure"
    DISK_FULL = "disk_full"
    CLOSED = "closed"
    STALLED = "stalled"


class ComputeCode(StrEnum):
    """Failure codes for numeric analysis."""

    TOO_FEW_POINTS = "too_few_points"
    DEGENERATE = "degenerate"
    NOT_FINITE = "not_finite"


class JobCode(StrEnum):
    """Failure codes for background jobs."""

    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    WORKER_CRASHED = "worker_crashed"
    TASK_FAILED = "task_failed"
    SLOT_BUSY = "slot_busy"
    SHUTTING_DOWN = "shutting_down"


# Every code maps to a "what to do" hint; tests assert the tables are complete.
_HINTS: dict[StrEnum, str] = {
    DeviceCode.NOT_FOUND: "Plug in the SADI board by USB and press Reconnect.",
    DeviceCode.DISCONNECTED: "Check the USB cable, then press Reconnect; recorded data is safe.",
    DeviceCode.TIMEOUT: "The board stopped answering; unplug it, plug it back in and retry.",
    DeviceCode.PROTOCOL: "Unexpected data from the board; reconnect it and retry the step.",
    DeviceCode.SATURATED: "LVDT is near +/-5 V; slide the core back toward the coil centre.",
    InputCode.OUT_OF_RANGE: "Enter a value inside the allowed range shown next to the field.",
    InputCode.MISSING: "Fill in the required field before continuing.",
    InputCode.DUPLICATE: "That name is already used; choose a different one.",
    InputCode.UNKNOWN_ID: "Pick an existing item from the list.",
    InputCode.BAD_UNIT: "Use SI units (m, kg, N, Pa, V, s); conversion happens only on screen.",
    StoreCode.IO: "Check free disk space and folder permissions, then retry.",
    StoreCode.CORRUPT: "The session file is damaged; reopen it to recover from the raw log.",
    StoreCode.LOCKED: "Another SADI window has this session open; close it first.",
    StoreCode.VERSION: "This session was made by a different SADI version; update the app.",
    StoreCode.BACKPRESSURE: "The data disk is slow; acquisition must pause. Data already shown is safe.",
    StoreCode.DISK_FULL: "The data disk is full. Data already shown is safe; free space, then retry.",
    StoreCode.CLOSED: "The recording is closed; open or start a session to record again.",
    StoreCode.STALLED: "The data disk is not responding; free space or change disk, then resume.",
    ComputeCode.TOO_FEW_POINTS: "Capture more points; at least 3 are needed for an uncertainty.",
    ComputeCode.DEGENERATE: "Points do not span enough range; capture points at distinct loads.",
    ComputeCode.NOT_FINITE: "A value is NaN or infinite; recheck the readings that feed it.",
    JobCode.CANCELLED: "The calculation was cancelled; start it again if you still need it.",
    JobCode.SUPERSEDED: "A newer calculation replaced this one; no action needed.",
    JobCode.FAILED: "The calculation failed; retry, and report it if it repeats.",
    JobCode.UNKNOWN: "That calculation is no longer running; nothing to do.",
    JobCode.WORKER_CRASHED: "The calculation process crashed; retry, and report it if it repeats.",
    JobCode.TASK_FAILED: "The calculation raised an error; retry, and report it if it repeats.",
    JobCode.SLOT_BUSY: "All calculation workers are busy; try again in a moment.",
    JobCode.SHUTTING_DOWN: "SADI is closing; calculations are no longer accepted.",
}

_STATUS: dict[ErrorFamily, int] = {
    ErrorFamily.DEVICE: 503,
    ErrorFamily.INPUT: 422,
    ErrorFamily.STORE: 500,
    ErrorFamily.COMPUTE: 422,
    ErrorFamily.JOB: 409,
}


def hint_for(code: StrEnum) -> str:
    """Return the user-facing 'what to do' hint for an error code."""
    return _HINTS[code]


class SadiError(BaseModel):
    """Frozen base error value; subclasses fix `family` and the `code` enum."""

    model_config = ConfigDict(frozen=True)

    family: ClassVar[ErrorFamily]
    code: StrEnum
    detail: str = ""

    @property
    def hint(self) -> str:
        """User-facing 'what to do' text for this error."""
        return hint_for(self.code)

    @property
    def status(self) -> int:
        """HTTP status the API maps this error to."""
        return _STATUS[self.family]

    def problem(self) -> dict[str, str | int]:
        """Return the RFC 7807 problem-JSON body (type, title, status, detail, hint)."""
        _log.debug("problem json for %s/%s", self.family, self.code)
        return {
            "type": f"urn:sadi:error:{self.family}:{self.code}",
            "title": self.code.replace("_", " "),
            "status": self.status,
            "detail": self.detail,
            "hint": self.hint,
        }


class DeviceError(SadiError):
    """Board or transport failure."""

    family: ClassVar[ErrorFamily] = ErrorFamily.DEVICE
    code: DeviceCode


class InputError(SadiError):
    """Invalid or missing user input."""

    family: ClassVar[ErrorFamily] = ErrorFamily.INPUT
    code: InputCode


class StoreError(SadiError):
    """Durable-storage failure."""

    family: ClassVar[ErrorFamily] = ErrorFamily.STORE
    code: StoreCode


class ComputeError(SadiError):
    """Numeric analysis failure."""

    family: ClassVar[ErrorFamily] = ErrorFamily.COMPUTE
    code: ComputeCode


class JobError(SadiError):
    """Background-job failure."""

    family: ClassVar[ErrorFamily] = ErrorFamily.JOB
    code: JobCode


ERROR_TYPES: tuple[type[SadiError], ...] = (
    DeviceError,
    InputError,
    StoreError,
    ComputeError,
    JobError,
)
