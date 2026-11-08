"""BRW checks: can SADI open a browser."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from sadi.doctor.registry import Ctx, Fix, Outcome, check, ok, remedy, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity
from sadi.doctor.steps import action, cmd, manual


@check(
    "BRW-010",
    Layer.BRW,
    "A browser can be launched",
    Severity.WARNING,
    {
        "no-browser": "No browser controller resolves",
        "wsl-no-wslview": "WSL without wslview or a BROWSER setting",
    },
    "webbrowser.get(); WSL: wslview / BROWSER",
)
def brw_010(ctx: Ctx) -> Outcome:
    """Warn when launching the UI automatically will not work."""
    if ctx.os is Os.WSL and not ctx.probes.which("wslview") and not ctx.probes.env().get("BROWSER"):
        return warn("wsl-no-wslview", "WSL has no wslview and BROWSER is unset")
    if ctx.probes.browser_available():
        return ok("A browser controller is available")
    return warn("no-browser", "No browser found; SADI will print the URL instead")


@remedy("BRW-010", "no-browser")
def _brw_010_none(ctx: Ctx, out: Outcome) -> Fix:
    """Open the URL by hand."""
    return Fix(
        "Open the UI by hand",
        (
            manual(
                "When SADI starts it prints http://127.0.0.1:8000; paste it into any browser.",
                "The SADI page loads.",
                if_not="Install a browser (Firefox or Chrome) and set it as default.",
            ),
        ),
    )


@remedy("BRW-010", "wsl-no-wslview")
def _brw_010_wsl(ctx: Ctx, out: Outcome) -> Fix:
    """Install wslu or set BROWSER."""
    return Fix(
        "Let WSL open Windows browsers",
        (
            action(
                "Install wslu, which provides wslview.",
                "`which wslview` prints a path.",
                cmd(ctx.os, "sudo apt install wslu"),
                mutates=Mutates.INSTALL,
                changes="Installs the wslu package.",
                alt="export BROWSER=explorer.exe",
            ),
            action(
                "Open the running SADI in the browser.",  # frob:ticket 01M6WMZHNS2E0QNW7KFZ1GAYMZ
                "The SADI page loads.",
                cmd(ctx.os, "python3 -m webbrowser http://127.0.0.1:8000", fixable=True),
                mutates=Mutates.PROCESS,
                changes="Starts a browser window; changes no files.",
            ),
        ),
    )
