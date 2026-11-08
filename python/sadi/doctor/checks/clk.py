"""CLK checks: wall clock sanity."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from datetime import UTC, datetime

from sadi.doctor.registry import Ctx, Fix, Outcome, check, ok, remedy, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity
from sadi.doctor.steps import action, cmd, manual

#: Lower bound for a plausible clock: the date this check was written.
EARLIEST_PLAUSIBLE = datetime(2026, 1, 1, tzinfo=UTC)


@check(
    "CLK-010",
    Layer.CLK,
    "Wall clock plausible",
    Severity.WARNING,
    {"clock-before-build": "The system date is earlier than this SADI release"},
    "time.time() against the release date",
)
def clk_010(ctx: Ctx) -> Outcome:
    """Warn on a clock stuck in the past (session names sort by time)."""
    now = datetime.fromtimestamp(ctx.probes.now(), UTC)
    if now < EARLIEST_PLAUSIBLE:
        return warn(
            "clock-before-build",
            f"System date {now:%Y-%m-%d} is before this release",
            now=now.isoformat(),
        )
    return ok(f"System date {now:%Y-%m-%d}", now=now.isoformat())


@remedy("CLK-010", "clock-before-build")
def _clk_010_fix(ctx: Ctx, out: Outcome) -> Fix:
    """Resync the clock."""
    if ctx.os is Os.WINDOWS:
        sync = action(
            "Resync with the time server (administrator PowerShell).",
            "The command reports success.",
            cmd(ctx.os, "w32tm /resync"),
            mutates=Mutates.SYSTEM,
            changes="Sets the system clock from the network.",
        )
    elif ctx.os is Os.MACOS:
        sync = manual(
            "Open System Settings, General, Date & Time, and turn on automatic time.",
            "The clock shows the correct date.",
            mutates=Mutates.SYSTEM,
            changes="Enables network time sync.",
        )
    else:
        sync = action(
            "Enable network time sync.",
            "No output; `date` then shows the correct time.",
            cmd(ctx.os, "sudo timedatectl set-ntp true"),
            mutates=Mutates.SYSTEM,
            changes="Turns on NTP synchronisation.",
            if_not="WSL: run `wsl --shutdown` in PowerShell and reopen; the clock resyncs on start.",
        )
    return Fix("Correct the system clock", (sync,))
