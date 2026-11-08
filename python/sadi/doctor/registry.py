"""Check and remediation registry: decorators, the Outcome a check returns, catalog access."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from sadi.doctor.probes import Probes
from sadi.doctor.schema import (
    CheckId,
    CheckSpec,
    CommandRun,
    FactValue,
    Layer,
    ModeId,
    Os,
    RunOptions,
    Severity,
    SkipReason,
    Status,
    Step,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)


@dataclass(frozen=True)
class Ctx:
    """What a check or remedy may look at: probes, options, resolved OS and data root."""

    probes: Probes
    options: RunOptions
    os: Os
    data_root: str | None = None
    facts: Mapping[str, FactValue] = field(default_factory=dict)


@dataclass(frozen=True)
class Outcome:
    """What a check function returns; the runner turns it into a CheckResult."""

    status: Status
    headline: str
    mode: ModeId | None = None
    facts: Mapping[str, FactValue] = field(default_factory=dict)
    skip_reason: SkipReason | None = None
    commands: tuple[CommandRun, ...] = ()


@dataclass(frozen=True)
class Fix:
    """What a remedy returns: a one-line summary and the ordered steps (verify is appended)."""

    summary: str
    steps: tuple[Step, ...]
    docs: tuple[str, ...] = ()


def ok(headline: str, **facts: FactValue) -> Outcome:
    """Build a PASS outcome."""
    return Outcome(Status.PASS, headline, facts=facts)


def warn(mode: ModeId, headline: str, **facts: FactValue) -> Outcome:
    """Build a WARN outcome in a failure mode."""
    return Outcome(Status.WARN, headline, mode=mode, facts=facts)


def fail(mode: ModeId, headline: str, **facts: FactValue) -> Outcome:
    """Build a FAIL outcome in a failure mode."""
    return Outcome(Status.FAIL, headline, mode=mode, facts=facts)


def skip(reason: SkipReason, headline: str, **facts: FactValue) -> Outcome:
    """Build a SKIP outcome."""
    return Outcome(Status.SKIP, headline, skip_reason=reason, facts=facts)


CheckFn = Callable[[Ctx], Outcome]
RemedyFn = Callable[[Ctx, Outcome], Fix]

_CHECKS: dict[str, tuple[CheckSpec, CheckFn]] = {}
_REMEDIES: dict[tuple[str, str], RemedyFn] = {}
ALL_OS = frozenset(Os)


def check(
    id: CheckId,
    layer: Layer,
    title: str,
    severity: Severity,
    modes: dict[ModeId, str],
    detection: str,
    *,
    applies_to: frozenset[Os] = ALL_OS,
    depends_on: tuple[CheckId, ...] = (),
    opt_in_flag: str | None = None,
) -> Callable[[CheckFn], CheckFn]:
    """Register a check function under a catalog id."""

    def deco(fn: CheckFn) -> CheckFn:
        if id in _CHECKS:
            raise ValueError(f"duplicate check id {id}")
        spec = CheckSpec(
            id=id,
            layer=layer,
            title=title,
            severity=severity,
            applies_to=applies_to,
            depends_on=depends_on,
            opt_in_flag=opt_in_flag,
            modes=modes,
            detection=detection,
        )
        _CHECKS[id] = (spec, fn)
        return fn

    return deco


def remedy(check_id: CheckId, mode: ModeId) -> Callable[[RemedyFn], RemedyFn]:
    """Register the remedy for one failure mode of a check (all OSes branch inside)."""

    def deco(fn: RemedyFn) -> RemedyFn:
        key = (check_id, mode)
        if key in _REMEDIES:
            raise ValueError(f"duplicate remedy {key}")
        _REMEDIES[key] = fn
        return fn

    return deco


def load_checks() -> None:
    """Import every checks module so the decorators run (idempotent)."""
    import sadi.doctor.checks  # noqa: F401


def all_checks() -> list[tuple[CheckSpec, CheckFn]]:
    """Return the catalog in layer order then id order."""
    load_checks()
    order = {layer: i for i, layer in enumerate(Layer)}
    return sorted(_CHECKS.values(), key=lambda t: (order[t[0].layer], t[0].id))


def get_remedy(check_id: str, mode: str) -> RemedyFn | None:
    """Return the remedy for a (check, mode), or None when missing."""
    load_checks()
    return _REMEDIES.get((check_id, mode))
