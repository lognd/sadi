"""RES checks: CPU, memory and file-descriptor budget."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity, SkipReason
from sadi.doctor.steps import action, cmd, manual

MIB = 1024**2
SERVER_NEED = 512 * MIB + 64 * MIB
WORKER_NEED = 256 * MIB
MIN_NOFILE = 1024


def worker_count(cpus: int) -> int:
    """Return the worker budget: max(1, min(4, cpus - 1))."""
    return max(1, min(4, cpus - 1))


@check(
    "RES-010",
    Layer.RES,
    "CPU count and worker budget",
    Severity.WARNING,
    {"single-core": "One CPU: workers compete with acquisition"},
    "os.cpu_count()",
)
def res_010(ctx: Ctx) -> Outcome:
    """Warn on a single-core machine."""
    cpus = ctx.probes.cpu_count()
    if cpus <= 1:
        return warn("single-core", "Only one CPU is available", cpus=cpus, workers=1)
    return ok(f"{cpus} CPUs, {worker_count(cpus)} workers", cpus=cpus, workers=worker_count(cpus))


@remedy("RES-010", "single-core")
def _res_010_fix(ctx: Ctx, out: Outcome) -> Fix:
    """Add CPUs or close programs."""
    return Fix(
        "Give SADI more than one CPU",
        (
            manual(
                "Close heavy programs while acquiring. On a virtual machine or WSL, raise the CPU count (WSL: `processors=` in .wslconfig).",
                "The doctor reports 2 or more CPUs.",
                if_not="Acquisition still works; analysis is slower.",
            ),
        ),
    )


@check(
    "RES-020",
    Layer.RES,
    "Available memory",
    Severity.WARNING,
    {
        "low-memory": "Less memory than the server plus all workers need",
        "very-low-memory": "Less memory than the server alone needs",
    },
    "psutil.virtual_memory().available vs 576 MiB + 256 MiB per worker",
)
def res_020(ctx: Ctx) -> Outcome:
    """Compare available RAM with the budget."""
    avail = ctx.probes.mem_available()
    if avail is None:
        return skip(SkipReason.TOOL_MISSING, "Could not read available memory")
    workers = worker_count(ctx.probes.cpu_count())
    need = SERVER_NEED + workers * WORKER_NEED
    facts = {"available_mib": avail // MIB, "need_mib": need // MIB}
    if avail < SERVER_NEED:
        return fail(
            "very-low-memory",
            f"{avail // MIB} MiB available; the server needs {SERVER_NEED // MIB}",
            **facts,
        )
    if avail < need:
        return warn(
            "low-memory", f"{avail // MIB} MiB available; {need // MIB} recommended", **facts
        )
    return ok(f"{avail // MIB} MiB available", **facts)


def _memory_fix(ctx: Ctx) -> Fix:
    """Shared memory remedy."""
    show = (
        "Get-Process | Sort-Object WS -Descending | Select-Object -First 5 Name,WS"
        if ctx.os is Os.WINDOWS
        else "ps aux --sort=-rss | head -n 6"
    )
    return Fix(
        "Free memory",
        (
            action(
                "List the biggest memory users.", "A short list of processes.", cmd(ctx.os, show)
            ),
            manual(
                "Close the ones you do not need (browser tabs are common).",
                "Available memory has grown.",
            ),
        ),
    )


@remedy("RES-020", "low-memory")
def _res_020_low(ctx: Ctx, out: Outcome) -> Fix:
    """Free memory."""
    return _memory_fix(ctx)


@remedy("RES-020", "very-low-memory")
def _res_020_very(ctx: Ctx, out: Outcome) -> Fix:
    """Free memory."""
    return _memory_fix(ctx)


@check(
    "RES-030",
    Layer.RES,
    "Open-file limit",
    Severity.WARNING,
    {"low-nofile": "Soft open-file limit under 1024"},
    "resource.getrlimit(RLIMIT_NOFILE) soft limit (POSIX)",
    applies_to=frozenset({Os.LINUX, Os.MACOS, Os.WSL}),
)
def res_030(ctx: Ctx) -> Outcome:
    """Warn on a tiny descriptor limit."""
    soft = ctx.probes.nofile_soft()
    if soft is None:
        return skip(SkipReason.TOOL_MISSING, "Could not read the limit")
    if soft < MIN_NOFILE:
        return warn("low-nofile", f"Soft limit is {soft}", soft=soft)
    return ok(f"Soft limit is {soft}", soft=soft)


@remedy("RES-030", "low-nofile")
def _res_030_fix(ctx: Ctx, out: Outcome) -> Fix:
    """Raise the limit for this shell."""
    return Fix(
        "Raise the open-file limit",
        (
            action(
                "Raise the limit for this shell, then start SADI from it.",
                "No output.",
                cmd(ctx.os, "ulimit -n 4096"),
                mutates=Mutates.PROCESS,
                changes="Raises the soft limit for this shell only.",
                if_not="The hard limit is lower; ask an administrator to raise it.",
            ),
        ),
    )
