"""WEB checks: the packaged UI bundle."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy
from sadi.doctor.schema import Layer, Mutates, Severity
from sadi.doctor.steps import action, cmd


@check(
    "WEB-010",
    Layer.WEB,
    "Built UI bundle present",
    Severity.BLOCKER,
    {"missing-bundle": "sadi/web/dist/index.html is absent or empty"},
    "sadi/web/dist/index.html exists and is non-empty",
)
def web_010(ctx: Ctx) -> Outcome:
    """Confirm the UI bundle was built."""
    present, size = ctx.probes.web_bundle()
    if not present or size == 0:
        return fail(
            "missing-bundle", "The UI bundle (index.html) is missing", present=present, size=size
        )
    return ok("UI bundle present", size=size)


@remedy("WEB-010", "missing-bundle")
def _web_010_missing(ctx: Ctx, out: Outcome) -> Fix:
    """Build the UI."""
    return Fix(
        "Build the web UI",
        (
            action(
                "Install the UI dependencies (needs Node.js 20 or newer).",
                "npm finishes with no errors.",
                cmd(ctx.os, "npm ci", context="in the repository's web/ directory"),
                mutates=Mutates.INSTALL,
                changes="Creates web/node_modules.",
                if_not="Install Node.js from nodejs.org and repeat.",
            ),
            action(
                "Build the bundle into the Python package.",
                "Vite prints 'built in' and python/sadi/web/dist/index.html exists.",
                cmd(ctx.os, "npm run build", context="in the repository's web/ directory"),
                mutates=Mutates.INSTALL,
                changes="Writes python/sadi/web/dist.",
            ),
        ),
    )
