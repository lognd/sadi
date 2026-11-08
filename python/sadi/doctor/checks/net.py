"""NET checks: loopback and the API port."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy
from sadi.doctor.schema import Layer, Os, Severity
from sadi.doctor.steps import action, cmd, manual

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
