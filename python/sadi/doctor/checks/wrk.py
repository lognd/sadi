"""WRK checks: background worker processes can be started and are cleaned up."""

# frob:ticket 01M6WJHVRVS94M67F41C3P2BMG
from __future__ import annotations

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity
from sadi.doctor.steps import action, cmd, manual

_SLOW_WINDOWS_S = 10.0
_PY = ("PY-020",)


@check(
    "WRK-010",
    Layer.WRK,
    "Worker process spawns",
    Severity.ERROR,
    {
        "spawn-fail": "A spawned worker did not start or did not answer",
        "spawn-slow": "Spawning a worker takes very long",
        "child-imports-store": "The worker pulled in the store, which it must not",
    },
    "Spawn a child (spawn context), round-trip a pydantic message, list its loaded modules",
    depends_on=_PY,
)
def wrk_010(ctx: Ctx) -> Outcome:
    """Spawn a self-test worker and judge its start-up."""
    facts = ctx.probes.worker_facts()
    secs = round(facts.spawn_seconds, 2)
    if facts.spawn_status != "ok":
        return fail(
            "spawn-fail",
            f"The worker did not start ({facts.spawn_status})",
            detail=facts.detail,
            seconds=secs,
        )
    if facts.imports_store:
        return fail("child-imports-store", "The worker imported sadi.store", detail=facts.detail)
    if ctx.os is Os.WINDOWS and facts.spawn_seconds > _SLOW_WINDOWS_S:
        return warn("spawn-slow", f"Spawning took {secs} s", seconds=secs)
    return ok(f"Worker started in {secs} s", seconds=secs)


@remedy("WRK-010", "spawn-fail")
def _wrk_010_fail(ctx: Ctx, out: Outcome) -> Fix:
    """Check the Python environment can spawn processes."""
    steps = [
        action(
            "Check the environment imports cleanly in a fresh process.",
            "Prints ok.",
            cmd(ctx.os, "python -c \"import sadi; print('ok')\""),
            if_not="Fix the PY checks first.",
        ),
        manual(
            "Close other heavy programs; a starved machine can miss the start-up timeout.",
            "Re-running the doctor passes.",
        ),
    ]
    if ctx.os is Os.WINDOWS:
        steps.append(
            manual(
                "Security software may block new Python processes: add the SADI folder "
                "to its exclusions, then re-run.",
                "The worker starts.",
            )
        )
    return Fix("Get workers starting", tuple(steps))


@remedy("WRK-010", "spawn-slow")
def _wrk_010_slow(ctx: Ctx, out: Outcome) -> Fix:
    """Antivirus scanning is the usual cause."""
    return Fix(
        "Speed up worker start-up",
        (
            manual(
                "Exclude the SADI folder and its Python environment from real-time antivirus "
                "scanning (Windows Security, Virus & threat protection, Exclusions).",
                "Spawning takes under 10 seconds.",
                mutates=Mutates.SYSTEM,
                changes="Adds a security-software exclusion.",
            ),
        ),
    )


@remedy("WRK-010", "child-imports-store")
def _wrk_010_store(ctx: Ctx, out: Outcome) -> Fix:
    """This is a code defect, not a setup problem."""
    return Fix(
        "Report the defect",
        (
            manual(
                "A worker must never open the data store. Keep the doctor report and file "
                "a bug naming the module shown in the detail.",
                "A bug is filed.",
            ),
        ),
    )


@check(
    "WRK-020",
    Layer.WRK,
    "Orphaned workers exit",
    Severity.WARNING,
    {"orphan-survives": "A worker kept running after its parent went away"},
    "Spawn a watchdog child, close the parent end, expect it to exit within 5 seconds",
    depends_on=_PY,
)
def wrk_020(ctx: Ctx) -> Outcome:
    """Check a worker exits when its parent is gone."""
    facts = ctx.probes.worker_facts()
    if facts.orphan_survives:
        return warn("orphan-survives", "A worker outlived its parent")
    return ok("Workers exit with their parent")


@remedy("WRK-020", "orphan-survives")
def _wrk_020_orphan(ctx: Ctx, out: Outcome) -> Fix:
    """List and end stray workers."""
    if ctx.os is Os.WINDOWS:
        find = action(
            "List stray Python processes.",
            "Only processes you recognise are listed.",
            cmd(ctx.os, "Get-Process python | Select-Object Id, StartTime, Path"),
        )
    else:
        find = action(
            "List stray Python processes.",
            "Only processes you recognise are listed.",
            cmd(ctx.os, "ps -eo pid,etime,cmd | grep -i '[p]ython'"),
        )
    return Fix(
        "End leftover workers",
        (
            find,
            manual(
                "End any stray worker you recognise as SADI's, then report the defect.",
                "No stray workers remain.",
                mutates=Mutates.PROCESS,
                changes="Ends the processes you choose.",
            ),
        ),
    )
