"""Result schema of `sadi doctor`: frozen pydantic models shared by CLI, JSON and the UI."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)
from typani import ErrorSet


class DoctorError(ErrorSet):
    """Failure modes of starting a doctor run (not of a check, which reports a status)."""

    UnknownCheck = "A requested check id is not in the catalog; run `sadi-doctor list`"
    UnknownLayer = "A requested layer is not in the catalog; run `sadi-doctor list`"
    BundleExists = "The bundle path already exists; the doctor never overwrites, pick a new path"
    BundleInsideDataRoot = "The bundle path is inside the data root; choose a path outside it"
    FixNeedsTerminal = "--yes without a terminal also needs --non-interactive"
    BundleWriteFailed = "The bundle could not be written; see the log for the OS error"


class Layer(StrEnum):
    """Subsystem a check belongs to; also the run order."""

    PLAT = "plat"
    PY = "py"
    EXT = "ext"
    WEB = "web"
    NET = "net"
    DATA = "data"
    SESS = "sess"
    WAL = "wal"
    USB = "usb"
    DEV = "dev"
    AD3 = "ad3"
    SIM = "sim"
    CLK = "clk"
    RES = "res"
    WRK = "wrk"
    BRW = "brw"
    PLG = "plg"


class Severity(StrEnum):
    """How bad a fail of this check is for the user."""

    BLOCKER = "blocker"
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class Status(StrEnum):
    """Outcome of one run of one check."""

    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


class Os(StrEnum):
    """Detected host OS; WSL is distinct because its fixes differ."""

    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    WSL = "wsl"


class Shell(StrEnum):
    """Shell a command line is written for; drives the prompt glyph."""

    SH = "sh"
    POWERSHELL = "powershell"
    CMD = "cmd"


class Mutates(StrEnum):
    """Mutation class of a step."""

    NONE = "none"
    PROCESS = "process"
    SYSTEM = "system"
    INSTALL = "install"
    DATA_DIR = "data-dir"
    DATA = "data"


class StepKind(StrEnum):
    """Role of a step; the last step of a remediation must be VERIFY."""

    ACTION = "action"
    MANUAL = "manual"
    VERIFY = "verify"


class SkipReason(StrEnum):
    """Why a check did not run."""

    NOT_APPLICABLE_OS = "not-applicable-os"
    PREREQUISITE_FAILED = "prerequisite-failed"
    OPT_IN = "opt-in"
    READ_ONLY = "read-only"
    PORT_BUSY = "port-busy"
    TOOL_MISSING = "tool-missing"
    TIMEOUT = "timeout"
    DISABLED = "disabled"
    UNVERIFIED = "unverified"
    NO_DEVICE = "no-device"


CheckId = Annotated[str, StringConstraints(pattern=r"^[A-Z][A-Z0-9]{1,3}-\d{3}$")]
ModeId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]

_FROZEN = ConfigDict(frozen=True, extra="forbid")


class Command(BaseModel):
    """One copy-paste command line of a step."""

    model_config = _FROZEN
    shell: Shell
    line: str
    context: str | None = None
    fixable: bool = False


class Step(BaseModel):
    """One numbered remediation step with expected output."""

    model_config = _FROZEN
    kind: StepKind
    text: str
    commands: tuple[Command, ...] = ()
    expect: str
    mutates: Mutates = Mutates.NONE
    changes: str | None = None
    if_not: str | None = None
    alt: str | None = None

    @model_validator(mode="after")
    def _changes_required(self) -> Self:
        """A mutating step must say what it changes; a data step never has a command."""
        if self.mutates is not Mutates.NONE and not bool(self.changes):
            raise ValueError("mutating step needs `changes`")
        if self.mutates is Mutates.DATA and self.commands:
            raise ValueError("data steps are app actions, never commands")
        return self


class Remediation(BaseModel):
    """Ordered steps for one (check, mode, os) triple."""

    model_config = _FROZEN
    check_id: CheckId
    mode: ModeId
    os: Os
    summary: str
    steps: tuple[Step, ...] = Field(min_length=2)
    docs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _ends_with_verify(self) -> Self:
        """Every remediation re-runs its check as the last step."""
        if self.steps[-1].kind is not StepKind.VERIFY:
            raise ValueError("last step must be verify")
        return self


class CommandRun(BaseModel):
    """A read-only external command the doctor executed, for transparency."""

    model_config = _FROZEN
    argv: tuple[str, ...]
    exit_code: int | None
    stdout_tail: str = ""
    stderr_tail: str = ""
    duration_ms: int = 0


class ProbeError(BaseModel):
    """A probe raised or timed out; the check fails with this attached."""

    model_config = _FROZEN
    kind: Literal["exception", "timeout", "tool-missing"]
    detail: str


FactValue = str | int | float | bool | None | list[str]


class Evidence(BaseModel):
    """What the probes saw; shown under Details and emitted as JSON."""

    model_config = _FROZEN
    facts: dict[str, FactValue] = Field(default_factory=dict)
    commands_run: tuple[CommandRun, ...] = ()
    error: ProbeError | None = None


class CheckSpec(BaseModel):
    """Static description of a check from the registry (catalog row)."""

    model_config = _FROZEN
    id: CheckId
    layer: Layer
    title: str
    severity: Severity
    applies_to: frozenset[Os]
    depends_on: tuple[CheckId, ...] = ()
    opt_in_flag: str | None = None
    modes: dict[ModeId, str]
    detection: str


class CheckResult(BaseModel):
    """Outcome of one check in one run."""

    model_config = _FROZEN
    id: CheckId
    title: str
    layer: Layer
    severity: Severity
    status: Status
    headline: str
    mode: ModeId | None = None
    skip_reason: SkipReason | None = None
    evidence: Evidence
    remediation: Remediation | None = None
    duration_ms: int

    @model_validator(mode="after")
    def _consistency(self) -> Self:
        """warn/fail carry a mode and a remediation; skip carries a reason."""
        if self.status in (Status.WARN, Status.FAIL) and (
            self.mode is None or self.remediation is None
        ):
            raise ValueError("warn/fail need mode and remediation")
        if self.status is Status.SKIP and self.skip_reason is None:
            raise ValueError("skip needs skip_reason")
        return self


class Host(BaseModel):
    """Where the run happened."""

    model_config = _FROZEN
    os: Os
    os_version: str
    arch: str
    python: str
    sadi_version: str
    sadi_py_version: str | None = None
    hostname_hash: str
    data_root: str | None = None
    wsl_distro: str | None = None


class RunOptions(BaseModel):
    """Flags that shaped the run; recorded so a report is reproducible."""

    model_config = _FROZEN
    checks: tuple[CheckId, ...] | None = None
    layers: tuple[Layer, ...] | None = None
    skip: tuple[CheckId, ...] = ()
    deep: bool = False
    with_reset: bool = False
    stream_seconds: int = 0
    ad3_open: bool = False  # frob:ticket 01M6Z1E0F6PK6K2F6B9VC7QQWM
    allow_probe_write: bool = False
    allow_network_fs: bool = False
    render_os: Os | None = None
    port: str | None = None
    api_port: int = 8000
    running: bool = False
    open_browser: bool = False  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    data_root: str | None = None


class Summary(BaseModel):
    """Counts and the overall verdict."""

    model_config = _FROZEN
    counts: dict[Status, int]
    worst_severity_failed: Severity | None
    verdict: Literal["ready", "degraded", "blocked"]
    first_action: str | None


class DoctorReport(BaseModel):
    """Whole run: the JSON document and the UI screen's state."""

    model_config = _FROZEN
    schema_version: Literal[1] = 1
    run_id: UUID
    started_at: AwareDatetime
    finished_at: AwareDatetime
    host: Host
    options: RunOptions
    results: tuple[CheckResult, ...]
    summary: Summary
    log_path: str | None = None
