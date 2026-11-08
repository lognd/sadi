"""BRW checks: can SADI open a browser."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from sadi.doctor.registry import Ctx, Fix, Outcome, check, ok, remedy, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity
from sadi.doctor.steps import action, cmd, manual
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

MIN_BROWSER = {"chromium": 110, "firefox": 115, "safari": 16}
LAUNCH_WAIT_S = 10.0


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
    if (
        ctx.os is Os.WSL
        and not bool(ctx.probes.which("wslview"))
        and not bool(ctx.probes.env().get("BROWSER"))
    ):
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


@check(
    "BRW-020",
    Layer.BRW,
    "Browser is supported",
    Severity.INFO,
    {
        "old-browser": "The default browser is older than Chromium 110, Firefox 115 or Safari 16",
        "unknown-browser": "The default browser or its version could not be determined",
    },
    "registry (Windows), defaults read (macOS Safari), --version of the resolved binary",
)  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
def brw_020(ctx: Ctx) -> Outcome:
    """Warn when the default browser is too old for the UI, or cannot be identified."""
    found = ctx.probes.browser_version()
    if found is None:
        return warn("unknown-browser", "Could not identify the default browser's version")
    family, major = found
    minimum = MIN_BROWSER[family]
    _log.debug("browser %s %d (minimum %d)", family, major, minimum)
    if major < minimum:
        return warn(
            "old-browser",
            f"{family} {major} is older than the supported {minimum}",
            family=family,
            major=major,
            minimum=minimum,
        )
    return ok(f"{family} {major} is supported", family=family, major=major, minimum=minimum)


@remedy("BRW-020", "old-browser")
def _brw_020_old(ctx: Ctx, out: Outcome) -> Fix:  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    """Update the browser."""
    return Fix(
        "Update the browser",
        (
            manual(
                "Update your browser to Chromium 110, Firefox 115, Safari 16 or newer.",
                "The browser's About page shows a supported version.",
                if_not="Install a current Firefox or Chrome and make it the default.",
            ),
        ),
    )


@remedy("BRW-020", "unknown-browser")
def _brw_020_unknown(ctx: Ctx, out: Outcome) -> Fix:  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    """Confirm the browser version by hand."""
    return Fix(
        "Check the browser version by hand",
        (
            manual(
                "Open your browser's About page and read its version.",
                "Chromium 110, Firefox 115, Safari 16 or newer.",
                if_not="Update or install a current browser.",
            ),
        ),
    )


@check(
    "BRW-030",
    Layer.BRW,
    "Launch dry run",
    Severity.INFO,
    {"launch-no-hit": "A browser started but never fetched the throwaway page"},
    "open http://127.0.0.1:<port>/doctor-ping on a throwaway listener; wait 10 s for the GET",
    opt_in_flag="open_browser",
)  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
def brw_030(ctx: Ctx) -> Outcome:
    """Warn when opening the browser does not reach a local listener."""
    if ctx.probes.browser_launch_hit(LAUNCH_WAIT_S):
        return ok("The browser fetched the throwaway page")
    return warn(
        "launch-no-hit",
        "A browser was asked to open but never fetched the page",
        waited_s=LAUNCH_WAIT_S,
    )


@remedy("BRW-030", "launch-no-hit")
def _brw_030_nohit(ctx: Ctx, out: Outcome) -> Fix:  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    """Check the default browser and proxy."""
    return Fix(
        "Find out why the browser did not reach localhost",
        (
            manual(
                "Open http://127.0.0.1:8000 in the browser by hand once SADI is running.",
                "The SADI page loads.",
                if_not="Check the default-browser setting and that no proxy intercepts 127.0.0.1 (NET-030).",
            ),
        ),
    )
