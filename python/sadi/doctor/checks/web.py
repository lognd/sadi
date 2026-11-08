"""WEB checks: the packaged UI bundle."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Mutates, Severity, SkipReason
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


@check(
    "WEB-020",
    Layer.WEB,
    "Bundle version matches the server",
    Severity.WARNING,
    {"stale-bundle": "dist/version.json names a different SADI version than the installed one"},
    "sadi/web/dist/version.json 'sadi' vs the installed sadi version",
)  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
def web_020(ctx: Ctx) -> Outcome:
    """Warn when the UI bundle was built for another SADI version."""
    bundled = ctx.probes.web_bundle_version()
    if bundled is None:
        return skip(SkipReason.UNVERIFIED, "The bundle records no version (dist/version.json)")
    server = ctx.probes.dist_version("sadi")
    if server is not None and bundled != server:
        return warn(
            "stale-bundle",
            f"The UI bundle is for SADI {bundled} but {server} is installed",
            bundle=bundled,
            server=server,
        )
    return ok(f"UI bundle matches SADI {bundled}", bundle=bundled, server=server)


@remedy("WEB-020", "stale-bundle")
def _web_020_stale(ctx: Ctx, out: Outcome) -> Fix:  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    """Rebuild the UI."""
    return Fix(
        "Rebuild the web UI",
        (
            action(
                "Rebuild the bundle so it matches this SADI version.",
                "Vite prints 'built in' and dist/version.json names the installed version.",
                cmd(ctx.os, "npm run build", context="in the repository's web/ directory"),
                mutates=Mutates.INSTALL,
                changes="Rewrites python/sadi/web/dist.",
                if_not="Reinstall SADI so the wheel and its bundle agree.",
            ),
        ),
    )
