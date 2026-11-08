"""CLK checks: wall clock sanity."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from datetime import UTC, datetime

from sadi.doctor.registry import Ctx, Fix, Outcome, check, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity, SkipReason
from sadi.doctor.steps import action, cmd, manual

#: Lower bound for a plausible clock: the date this check was written.
EARLIEST_PLAUSIBLE = datetime(2026, 1, 1, tzinfo=UTC)
#: Monotonic resolution above this (seconds) makes mono_ns stamps coarse.
COARSE_RESOLUTION_S = 1e-3
SYNC_COMMANDS = {
    Os.LINUX: ("timedatectl", "show", "-p", "NTPSynchronized"),
    Os.WSL: ("timedatectl", "show", "-p", "NTPSynchronized"),
    Os.MACOS: ("systemsetup", "-getusingnetworktime"),
    Os.WINDOWS: ("w32tm", "/query", "/status"),
}


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


@check(
    "CLK-020",
    Layer.CLK,
    "Monotonic clock resolution",
    Severity.INFO,
    {"coarse-monotonic": "Monotonic clock resolution is over 1 ms; mono_ns in RAW_BLOCK is coarse"},
    "time.get_clock_info('monotonic').resolution (Windows timer resolution is not queried)",
)
def clk_020(ctx: Ctx) -> Outcome:
    """Report a coarse monotonic clock (informational: only RAW_BLOCK timestamps suffer)."""
    res = ctx.probes.monotonic_resolution()
    if res > COARSE_RESOLUTION_S:
        return warn("coarse-monotonic", f"Resolution is {res * 1000:.1f} ms", resolution_s=res)
    return ok(f"Resolution is {res * 1e9:.0f} ns", resolution_s=res)


@remedy("CLK-020", "coarse-monotonic")
def _clk_020_fix(ctx: Ctx, out: Outcome) -> Fix:
    """Explain the limitation; nothing to repair."""
    if ctx.os is Os.WINDOWS:
        step = manual(
            "Close programs that lower the timer resolution, or restart; Windows picks the finest timer any program requests.",
            "The doctor reports a resolution under 1 ms.",
            if_not="Only mono_ns in RAW_BLOCK is affected; measurements stay correct.",
        )
    else:
        step = manual(
            "No action needed; only mono_ns in RAW_BLOCK is affected and measurements stay correct.",
            "The doctor reports a resolution under 1 ms.",
            if_not="Virtual machines and containers often have coarse clocks.",
        )
    return Fix("Accept the coarse monotonic clock", (step,))


@check(
    "CLK-030",
    Layer.CLK,
    "Timezone resolvable",
    Severity.INFO,
    {"tz-unknown": "The local timezone cannot be determined; the UI shows UTC"},
    "datetime.now().astimezone().tzname()",
)
def clk_030(ctx: Ctx) -> Outcome:
    """Report an unresolvable local timezone."""
    name = ctx.probes.tz_name()
    if not name:
        return warn("tz-unknown", "Timezone could not be determined")
    return ok(f"Timezone is {name}", tz=name)


@remedy("CLK-030", "tz-unknown")
def _clk_030_fix(ctx: Ctx, out: Outcome) -> Fix:
    """Set the system timezone."""
    if ctx.os is Os.WINDOWS:
        step = action(
            "List the current timezone.",
            "A timezone name; change it in Settings, Time & language, Date & time if wrong.",
            cmd(ctx.os, "Get-TimeZone"),
        )
    elif ctx.os is Os.MACOS:
        step = manual(
            "Open System Settings, General, Date & Time, and choose a time zone.",
            "The menu bar clock shows local time.",
            mutates=Mutates.SYSTEM,
            changes="Sets the system timezone.",
        )
    else:
        step = action(
            "Set the timezone (replace Europe/London with yours).",
            "No output; `date` shows local time.",
            cmd(ctx.os, "sudo timedatectl set-timezone Europe/London"),
            mutates=Mutates.SYSTEM,
            changes="Sets the system timezone.",
            if_not="Alternatively export TZ=Europe/London before starting SADI.",
        )
    return Fix("Set the timezone", (step,))


@check(
    "CLK-040",
    Layer.CLK,
    "Time sync status",
    Severity.INFO,
    {"not-synced": "The clock is not synchronised with a time server"},
    "timedatectl show -p NTPSynchronized (Linux); systemsetup -getusingnetworktime (macOS, may need admin); w32tm /query /status (Windows)",
)
def clk_040(ctx: Ctx) -> Outcome:
    """Report a clock that is not network synchronised."""
    res = ctx.probes.run(SYNC_COMMANDS[ctx.os])
    if res.is_err or res.unwrap().exit_code != 0:
        return skip(SkipReason.TOOL_MISSING, "Could not read the time sync state (may need admin)")
    text = res.unwrap().stdout_tail.lower()
    if ctx.os is Os.WINDOWS:
        synced = "local cmos clock" not in text and "free-running" not in text
    elif ctx.os is Os.MACOS:
        synced = "network time: on" in text
    else:
        synced = "ntpsynchronized=yes" in text
    if not synced:
        return warn("not-synced", "Clock is not synchronised with a time server")
    return ok("Clock is synchronised")


@remedy("CLK-040", "not-synced")
def _clk_040_fix(ctx: Ctx, out: Outcome) -> Fix:
    """Turn on network time (the same steps as CLK-010)."""
    return _sync_fix(ctx)


def _sync_fix(ctx: Ctx) -> Fix:
    """Build the enable-network-time fix per OS."""
    if ctx.os is Os.WINDOWS:
        step = action(
            "Resync with the time server (administrator PowerShell).",
            "The command reports success.",
            cmd(ctx.os, "w32tm /resync"),
            mutates=Mutates.SYSTEM,
            changes="Sets the system clock from the network.",
            if_not="Start the service first: `net start w32time`.",
        )
    elif ctx.os is Os.MACOS:
        step = action(
            "Turn on automatic time.",
            "No output.",
            cmd(ctx.os, "sudo systemsetup -setusingnetworktime on"),
            mutates=Mutates.SYSTEM,
            changes="Enables network time sync.",
        )
    else:
        step = action(
            "Enable network time sync.",
            "No output; `timedatectl` then shows synchronized: yes.",
            cmd(ctx.os, "sudo timedatectl set-ntp true"),
            mutates=Mutates.SYSTEM,
            changes="Turns on NTP synchronisation.",
            if_not="WSL: run `wsl --shutdown` in PowerShell and reopen.",
        )
    return Fix("Synchronise the clock", (step,))
