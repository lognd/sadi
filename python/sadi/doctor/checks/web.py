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
    {"missing-bundle": "No non-empty index.html in sadi/_ui or web/dist"},
    "sadi/_ui/index.html (else web/dist/index.html) exists and is non-empty",
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
    """Build the UI with the repo's packaging script (Vite -> python/sadi/_ui)."""
    return Fix(
        "Build the web UI",
        (
            action(
                "Check that Node.js 20 or newer and npm are installed.",
                "node prints v20 or higher.",
                cmd(ctx.os, "node --version"),
                if_not="Install Node.js 20+ from nodejs.org and repeat.",
            ),
            action(
                "Build the bundle (runs npm ci and the Vite build in web/, then copies web/dist "
                "into python/sadi/_ui, the folder the launcher serves).",
                "Vite prints 'built in' and python/sadi/_ui/index.html exists.",
                cmd(
                    ctx.os,
                    "python packaging/build_ui.py",
                    context="in the repository root, using the SADI Python environment",
                    fixable=True,
                ),
                mutates=Mutates.INSTALL,
                changes="Creates web/node_modules, web/dist and python/sadi/_ui; nothing is deleted.",
                if_not="Read the npm error above; fix it and repeat. "
                "Without a bundle the launcher falls back to web/dist.",
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
