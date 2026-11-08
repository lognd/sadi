"""NET checks: loopback and the API port."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import re
from typing import Any

from sadi.doctor.checks.ext import child_json
from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Os, Severity, SkipReason
from sadi.doctor.steps import action, cmd, manual
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

_LOOPBACK = {"127.0.0.1", "::1"}
PRIVILEGED_PORT_MAX = 1023


@check(
    "NET-010",
    Layer.NET,
    "Loopback works",
    Severity.BLOCKER,
    {
        "no-loopback": "A one-byte TCP round trip on 127.0.0.1 failed",
        "localhost-not-loopback": "localhost resolves to a non-loopback address",
    },
    "bind 127.0.0.1:0, connect, echo one byte; getaddrinfo('localhost')",
)
def net_010(ctx: Ctx) -> Outcome:
    """Prove the loopback interface carries TCP and localhost resolves locally."""
    if not ctx.probes.loopback_ok():
        return fail("no-loopback", "A TCP round trip over 127.0.0.1 failed")
    addrs = ctx.probes.localhost_addrs()
    bad = [a for a in addrs if a not in _LOOPBACK]
    if bad:
        return fail(
            "localhost-not-loopback", f"localhost resolves to {', '.join(bad)}", addrs=addrs
        )
    return ok("Loopback works", addrs=addrs)


@remedy("NET-010", "no-loopback")
def _net_010_lo(ctx: Ctx, out: Outcome) -> Fix:
    """Diagnose a blocked loopback."""
    return Fix(
        "Restore the loopback interface",
        (
            manual(
                "Temporarily disable any firewall or security suite that filters 127.0.0.1 traffic.",
                "The security tool shows loopback allowed.",
                if_not="Try a different user account; a policy may block local sockets.",
            ),
        ),
    )


@remedy("NET-010", "localhost-not-loopback")
def _net_010_hosts(ctx: Ctx, out: Outcome) -> Fix:
    """Fix the hosts file."""
    path = r"C:\Windows\System32\drivers\etc\hosts" if ctx.os is Os.WINDOWS else "/etc/hosts"
    show = "Get-Content " + path if ctx.os is Os.WINDOWS else "cat " + path
    return Fix(
        "Point localhost back at the loopback address",
        (
            action(
                "Show the hosts file.",
                "A line `127.0.0.1 localhost` is present.",
                cmd(ctx.os, show),
            ),
            manual(
                "Edit the file as administrator so `localhost` maps to 127.0.0.1 and ::1 only.",
                "No other address is listed for localhost.",
            ),
        ),
    )


@check(
    "NET-020",
    Layer.NET,
    "API port available",
    Severity.ERROR,
    {
        "port-in-use-other": "Something already listens on the API port",
        "port-privileged": "Port below 1024 needs elevated rights",
        "bind-denied": "The OS refused the bind (reserved range or policy)",
    },
    "bind 127.0.0.1:<port> and release it at once",
    depends_on=("NET-010",),
)
def net_020(ctx: Ctx) -> Outcome:
    """Check the API port can be bound."""
    port = ctx.options.api_port
    state = ctx.probes.bind_state(port)
    if state == "free":
        return ok(f"Port {port} is free", port=port)
    if state == "in-use":
        return fail("port-in-use-other", f"Port {port} is already in use", port=port)
    if port <= PRIVILEGED_PORT_MAX and ctx.os is not Os.WINDOWS:
        return fail("port-privileged", f"Port {port} needs elevated rights", port=port)
    return fail("bind-denied", f"The OS refused to bind port {port}", port=port)


def _holder(ctx: Ctx, port: int) -> str:
    """Return the command that names the process on a port."""
    if ctx.os is Os.WINDOWS:
        return f"Get-NetTCPConnection -LocalPort {port} | Select-Object OwningProcess,State"
    if ctx.os is Os.MACOS:
        return f"lsof -nP -iTCP:{port} -sTCP:LISTEN"
    return f"ss -ltnp 'sport = :{port}'"


@remedy("NET-020", "port-in-use-other")
def _net_020_busy(ctx: Ctx, out: Outcome) -> Fix:
    """Find the holder or use another port."""
    port = ctx.options.api_port
    return Fix(
        f"Free port {port} or use another",
        (
            action(
                f"Find what is listening on port {port}.",
                "One line naming a process id.",
                cmd(ctx.os, _holder(ctx, port)),
                if_not="Nothing listed: it was transient; run the check again.",
            ),
            manual(
                "If that is an old SADI, stop it; otherwise start SADI on another port by setting SADI_API_PORT.",
                f"Port {port} is no longer listed.",
            ),
        ),
    )


@remedy("NET-020", "port-privileged")
def _net_020_priv(ctx: Ctx, out: Outcome) -> Fix:
    """Use an unprivileged port."""
    return Fix(
        "Use a port above 1023",
        (
            manual(
                "Start SADI with an unprivileged port, for example 8000 (SADI_API_PORT=8000).",
                "The doctor passes NET-020 with that port.",
            ),
        ),
    )


@remedy("NET-020", "bind-denied")
def _net_020_denied(ctx: Ctx, out: Outcome) -> Fix:
    """Show reserved ranges on Windows, else suggest another port."""
    steps = []
    if ctx.os is Os.WINDOWS:
        steps.append(
            action(
                "List the TCP port ranges Windows reserves.",
                "Your port is inside one of the listed ranges.",
                cmd(ctx.os, "netsh int ipv4 show excludedportrange protocol=tcp"),
            )
        )
    steps.append(
        manual(
            "Pick a port outside the reserved ranges and start SADI with SADI_API_PORT set to it.",
            "The doctor passes NET-020 with that port.",
        )
    )
    return Fix("Choose a port the OS allows", tuple(steps))


_PROXY_VARS = ("http_proxy", "https_proxy", "all_proxy")
_WININET_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Internet Settings"
_LOCAL_TOKENS = ("localhost", "127.0.0.1", "<local>", "127.*")
HEALTH_TIMEOUT_S = 2.0


def _env_ci(ctx: Ctx, name: str) -> str:
    """Return an environment variable by case-insensitive name, or an empty string."""
    for key, value in ctx.probes.env().items():
        if key.lower() == name:
            return value
    return ""


def _covers_local(exclusions: str) -> bool:
    """Report whether a no-proxy / ProxyOverride list excludes loopback."""
    items = [t.strip().lower() for t in re.split(r"[,;]", exclusions)]
    return "*" in items or any(t in _LOCAL_TOKENS for t in items)


def _wininet_value(ctx: Ctx, name: str) -> str:
    """Read one WinINET value via `reg query`; empty when absent."""
    res = ctx.probes.run(("reg", "query", _WININET_KEY, "/v", name))
    if res.is_err or res.unwrap().exit_code != 0:
        return ""
    parts = res.unwrap().stdout_tail.split()
    return parts[-1] if len(parts) >= 3 and parts[-3] == name else ""


@check(
    "NET-030",
    Layer.NET,
    "WebSocket allowed through local proxy settings",
    Severity.WARNING,
    {"proxy-intercepts-localhost": "A proxy is configured and does not exclude localhost"},
    "HTTP(S)_PROXY / NO_PROXY environment; Windows WinINET ProxyEnable / ProxyOverride",
)
def net_030(ctx: Ctx) -> Outcome:
    """Warn when a proxy would capture traffic to the local API and its WebSocket."""
    proxied = [v for v in _PROXY_VARS if _env_ci(ctx, v)]
    if proxied and not _covers_local(_env_ci(ctx, "no_proxy")):
        return warn(
            "proxy-intercepts-localhost",
            f"{', '.join(proxied)} set and NO_PROXY does not exclude localhost",
            source="environment",
            variables=proxied,
        )
    if ctx.os is Os.WINDOWS and _wininet_value(ctx, "ProxyEnable") == "0x1":
        if not _covers_local(_wininet_value(ctx, "ProxyOverride")):
            return warn(
                "proxy-intercepts-localhost",
                "The Windows system proxy is on and does not bypass localhost",
                source="wininet",
            )
    return ok("No proxy intercepts localhost")


@remedy("NET-030", "proxy-intercepts-localhost")
def _net_030_proxy(ctx: Ctx, out: Outcome) -> Fix:
    """Exclude loopback from the proxy."""
    if ctx.os is Os.WINDOWS:
        show = cmd(ctx.os, "Get-ChildItem Env: | Where-Object Name -like '*proxy*'")
        fix = "set NO_PROXY=localhost,127.0.0.1 for your user, and add <local> to the system proxy bypass list"
    else:
        show = cmd(ctx.os, "env | grep -i proxy")
        fix = "export NO_PROXY=localhost,127.0.0.1 in the shell that starts SADI"
    if ctx.os is Os.MACOS:
        extra = (cmd(ctx.os, "scutil --proxy"),)
    else:
        extra = ()
    return Fix(
        "Exclude localhost from the proxy",
        (
            action(
                "List the proxy settings that apply to this shell.",
                "You can see which variable names a proxy.",
                show,
                *extra,
            ),
            manual(
                f"To bypass the proxy for local traffic, {fix}.",
                "Opening the SADI page and its live view works without the proxy.",
            ),
        ),
    )


def health_script(port: int) -> str:
    """Return the child script that GETs the local health endpoint and prints a JSON summary."""
    return (
        "import json,urllib.request as u,urllib.error as e,socket\n"
        "try:\n"
        f" r=u.urlopen('http://127.0.0.1:{port}/api/health',timeout={HEALTH_TIMEOUT_S})\n"
        " b=json.loads(r.read() or b'{}')\n"
        " print(json.dumps({'status':r.status,'version':b.get('version')}))\n"
        "except e.HTTPError as x:\n"
        " print(json.dumps({'status':x.code,'version':None}))\n"
        "except (e.URLError,socket.timeout,OSError):\n"
        " print(json.dumps({'status':None,'version':None}))\n"
    )


@check(
    "NET-040",
    Layer.NET,
    "Launcher URL reachable",
    Severity.ERROR,
    {
        "health-timeout": "The running SADI did not answer /api/health in 2 s",
        "health-version-mismatch": "The running SADI is a different version",
        "health-500": "/api/health answered with a server error",
    },
    "--running only: GET http://127.0.0.1:<port>/api/health with a 2 s timeout; compare version",
    opt_in_flag="running",
)
def net_040(ctx: Ctx) -> Outcome:
    """Ask a running SADI for its health and version."""
    port = ctx.options.api_port
    got = child_json(ctx, health_script(port), HEALTH_TIMEOUT_S + 5.0)
    if got.is_err:
        return skip(
            SkipReason.TOOL_MISSING,
            "Could not run the health probe",
            detail=got.unwrap_err().detail,
        )
    info: dict[str, Any] = got.unwrap()
    status, version = info.get("status"), info.get("version")
    if status is None:
        return fail("health-timeout", f"Nothing answered on port {port}", port=port)
    if int(status) >= 500:
        return fail("health-500", f"/api/health answered {status}", port=port, status=int(status))
    mine = ctx.probes.dist_version("sadi")
    if version is not None and mine is not None and str(version) != mine:
        return fail(
            "health-version-mismatch",
            f"The running SADI is {version} but this install is {mine}",
            running=str(version),
            installed=mine,
        )
    _log.debug("NET-040 health status=%s version=%s", status, version)
    return ok(f"SADI answers on port {port}", port=port, status=int(status))


@remedy("NET-040", "health-timeout")
def _net_040_timeout(ctx: Ctx, out: Outcome) -> Fix:
    """Find out whether SADI is actually running."""
    port = ctx.options.api_port
    return Fix(
        "Check that SADI is running on this port",
        (
            action(
                f"See what listens on port {port}.",
                "One line naming the SADI process.",
                cmd(ctx.os, _holder(ctx, port)),
                if_not="Nothing listed: start SADI, or pass the right --api-port.",
            ),
        ),
    )


@remedy("NET-040", "health-version-mismatch")
def _net_040_version(ctx: Ctx, out: Outcome) -> Fix:
    """Stop the old SADI."""
    port = ctx.options.api_port
    return Fix(
        "Stop the other SADI and start this one",
        (
            action(
                f"Find the process holding port {port}.",
                "One line naming a process id.",
                cmd(ctx.os, _holder(ctx, port)),
            ),
            manual(
                "Stop that SADI, then start the one you just installed.",
                "The health version matches the installed version.",
            ),
        ),
    )


@remedy("NET-040", "health-500")
def _net_040_500(ctx: Ctx, out: Outcome) -> Fix:
    """Read the server log."""
    return Fix(
        "Find why the health endpoint fails",
        (
            manual(
                "Read the SADI server console for the traceback behind the 500.",
                "You can name the failing component.",
                if_not="Run `sadi-doctor --bundle` and send the bundle to the maintainers.",
            ),
        ),
    )
