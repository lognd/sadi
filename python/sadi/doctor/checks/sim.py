"""SIM checks: the built-in simulator works (no hardware needed)."""

# frob:ticket 01M6WJHVRVS94M67F41C3P2BMG
from __future__ import annotations

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip
from sadi.doctor.schema import Layer, Severity, SkipReason
from sadi.doctor.steps import action, cmd, manual

_EXT = ("EXT-010",)


def _repair_step(ctx: Ctx):  # noqa: ANN202 - Step type is internal to steps
    """Build the step that rebuilds the native extension."""
    return action(
        "Rebuild and reinstall the native extension.",
        "The command finishes without errors.",
        cmd(ctx.os, "uv sync --reinstall-package sadi_py"),
        if_not="Run the EXT checks (EXT-010 to EXT-030) and fix those first.",
    )


@check(
    "SIM-010",
    Layer.SIM,
    "Simulator connects and streams",
    Severity.ERROR,
    {
        "sim-connect-fail": "The simulator would not connect",
        "sim-data-mismatch": "The simulator's data is not what the ideal model gives",
        "sim-timeout": "The simulator did not deliver packets in time",
    },
    "sadi_py.open_sim with the clean scenario: connect, read, check continuity and finite volts",
    depends_on=_EXT,
)
def sim_010(ctx: Ctx) -> Outcome:
    """Run the clean simulator end to end."""
    facts = ctx.probes.sim_facts()
    if not facts.binding_ok:
        return skip(SkipReason.TOOL_MISSING, "sadi_py is not importable", detail=facts.detail)
    if facts.timed_out:
        return fail("sim-timeout", "The simulator timed out", detail=facts.detail)
    if not facts.connect_ok:
        return fail("sim-connect-fail", "The simulator did not connect", detail=facts.detail)
    if not facts.data_ok:
        return fail("sim-data-mismatch", "The simulator's data looks wrong", detail=facts.detail)
    return ok(f"Simulator streamed {facts.packets} packets", packets=facts.packets)


@remedy("SIM-010", "sim-connect-fail")
def _sim_010_connect(ctx: Ctx, out: Outcome) -> Fix:
    """Rebuild the extension."""
    return Fix("Repair the native extension", (_repair_step(ctx),))


@remedy("SIM-010", "sim-data-mismatch")
def _sim_010_data(ctx: Ctx, out: Outcome) -> Fix:
    """A wrong simulator means a stale or mismatched build."""
    return Fix(
        "Rebuild so the simulator matches this SADI",
        (
            _repair_step(ctx),
            manual(
                "If it still fails, keep the doctor report and file a bug: the simulator "
                "is deterministic, so this is a defect.",
                "The check passes, or a bug is filed.",
            ),
        ),
    )


@remedy("SIM-010", "sim-timeout")
def _sim_010_timeout(ctx: Ctx, out: Outcome) -> Fix:
    """A timeout is usually a starved machine."""
    return Fix(
        "Free the machine and retry",
        (
            manual(
                "Close heavy programs (and on a laptop, plug in the charger), then re-run.",
                "The check passes.",
                if_not="Rebuild the extension in the next step.",
            ),
            _repair_step(ctx),
        ),
    )


@check(
    "SIM-020",
    Layer.SIM,
    "All simulator scenarios load",
    Severity.WARNING,
    {"scenario-load-fail": "One or more scenarios cannot be constructed"},
    "Construct every scenario (clean, noisy, drifting, creeping, slipping, saturating, combined)",
    depends_on=_EXT,
)
def sim_020(ctx: Ctx) -> Outcome:
    """Construct each named scenario."""
    facts = ctx.probes.sim_facts()
    if not facts.binding_ok:
        return skip(SkipReason.TOOL_MISSING, "sadi_py is not importable", detail=facts.detail)
    if facts.failed_scenarios:
        names = list(facts.failed_scenarios)
        return fail(
            "scenario-load-fail", f"Scenarios failed to load: {', '.join(names)}", scenarios=names
        )
    return ok("All scenarios load")


@remedy("SIM-020", "scenario-load-fail")
def _sim_020_load(ctx: Ctx, out: Outcome) -> Fix:
    """Rebuild; scenarios live in the extension."""
    return Fix(
        "Repair the scenarios that failed to load",
        (_repair_step(ctx),),
    )
