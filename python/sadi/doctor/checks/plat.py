"""PLAT checks: OS, locale and environment."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import re

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity
from sadi.doctor.steps import action, cmd, manual

_MIN_MACOS = 12
_MIN_WINDOWS = 10


@check(
    "PLAT-010",
    Layer.PLAT,
    "Supported OS and version",
    Severity.BLOCKER,
    {
        "unsupported-os": "OS release older than Windows 10 / macOS 12",
        "wsl1": "WSL 1 has no USB path; use WSL 2 or Windows",
    },
    "platform.platform(), /proc/version on WSL",
)
def plat_010(ctx: Ctx) -> Outcome:
    """Reject unsupported releases and WSL 1."""
    version = ctx.probes.os_version()
    if ctx.os is Os.WSL:
        text = (ctx.probes.read_text("/proc/version") or "").lower()
        if "microsoft-standard" not in text and "wsl2" not in text:
            return fail("wsl1", "This is WSL 1, which cannot reach USB serial devices", os=version)
    match = re.search(r"(\d+)(?:\.\d+)*", version.split("-", 1)[-1])
    major = int(match.group(1)) if match else None
    if major is not None and (
        (ctx.os is Os.WINDOWS and major < _MIN_WINDOWS)
        or (ctx.os is Os.MACOS and major < _MIN_MACOS)
    ):
        return fail("unsupported-os", f"{version} is too old for SADI", os=version)
    return ok(f"{ctx.os.value} ({version}) is supported", os=version, arch=ctx.probes.machine())


@remedy("PLAT-010", "unsupported-os")
def _plat_010_old(ctx: Ctx, out: Outcome) -> Fix:
    """Tell the user to upgrade the OS."""
    return Fix(
        "Upgrade the operating system",
        (
            manual(
                "Upgrade to Windows 10 or newer, macOS 12 or newer, or a Linux with glibc 2.28+.",
                "The OS settings page shows a supported release.",
                if_not="Run SADI on another machine; older releases are not supported.",
            ),
        ),
    )


@remedy("PLAT-010", "wsl1")
def _plat_010_wsl1(ctx: Ctx, out: Outcome) -> Fix:
    """Convert the distro to WSL 2."""
    return Fix(
        "Convert this distro to WSL 2",
        (
            action(
                "In a Windows PowerShell window, list your distros and note this distro's name.",
                "A table with a VERSION column; this distro shows 1.",
                cmd(Os.WINDOWS, "wsl -l -v"),
            ),
            action(
                "Convert the distro (replace Ubuntu with the name from step 1).",
                "The conversion finishes with 'The operation completed successfully.'",
                cmd(Os.WINDOWS, "wsl --set-version Ubuntu 2"),
                mutates=Mutates.SYSTEM,
                changes="Converts the distro's filesystem to WSL 2 format; files are kept.",
                if_not="Run `wsl --update` and enable the Virtual Machine Platform feature.",
            ),
        ),
    )


@check(
    "PLAT-030",
    Layer.PLAT,
    "Locale and encoding",
    Severity.WARNING,
    {
        "non-utf8-console": "Console encoding is not UTF-8 and UTF-8 mode is off",
        "c-locale": "LANG is C/POSIX or unset",
    },
    "locale.getpreferredencoding(False), sys.flags.utf8_mode, LANG",
)
def plat_030(ctx: Ctx) -> Outcome:
    """Warn when units such as the micro sign would print as '?'."""
    enc, utf8_mode = ctx.probes.encoding()
    env = ctx.probes.env()
    facts = {"encoding": enc, "utf8_mode": utf8_mode, "lang": env.get("LANG")}
    if enc.lower().replace("-", "") == "utf8" or utf8_mode:
        return ok(f"Encoding is {enc}", **facts)
    lang = env.get("LC_ALL") or env.get("LANG") or ""
    if ctx.os in (Os.LINUX, Os.WSL) and lang in ("", "C", "POSIX"):
        return warn("c-locale", "Locale is C/POSIX; non-ASCII units will print as '?'", **facts)
    return warn("non-utf8-console", f"Console encoding is {enc}, not UTF-8", **facts)


@remedy("PLAT-030", "non-utf8-console")
def _plat_030_console(ctx: Ctx, out: Outcome) -> Fix:
    """Enable UTF-8 for this shell."""
    if ctx.os is Os.WINDOWS:
        step = action(
            "Turn on Python UTF-8 mode for this PowerShell session.",
            "No output.",
            cmd(ctx.os, "$env:PYTHONUTF8 = '1'"),
            mutates=Mutates.PROCESS,
            changes="Sets PYTHONUTF8 for this PowerShell window only.",
        )
    else:
        step = action(
            "Turn on Python UTF-8 mode for this shell.",
            "No output.",
            cmd(ctx.os, "export PYTHONUTF8=1"),
            mutates=Mutates.PROCESS,
            changes="Sets PYTHONUTF8 for this shell only.",
        )
    return Fix("Switch the console to UTF-8", (step,))


@remedy("PLAT-030", "c-locale")
def _plat_030_c(ctx: Ctx, out: Outcome) -> Fix:
    """Set a UTF-8 locale."""
    return Fix(
        "Use a UTF-8 locale",
        (
            action(
                "List installed UTF-8 locales.",
                "A line such as C.UTF-8 or en_US.utf8.",
                cmd(ctx.os, "locale -a | grep -i utf"),
            ),
            action(
                "Use one of them for this shell (replace C.UTF-8 with your choice).",
                "No output.",
                cmd(ctx.os, "export LANG=C.UTF-8"),
                mutates=Mutates.PROCESS,
                changes="Sets LANG for this shell only.",
                if_not="Generate one with your distro's locale tool, then repeat.",
            ),
        ),
    )


@check(
    "PLAT-050",
    Layer.PLAT,
    "Environment variables that change SADI behaviour",
    Severity.INFO,
    {"failpoints-armed": "SADI_FAILPOINTS is set: the store injects faults on purpose"},
    "SADI_* environment variables",
)
def plat_050(ctx: Ctx) -> Outcome:
    """Warn when fault injection is armed outside tests."""
    env = ctx.probes.env()
    sadi_vars = sorted(k for k in env if k.startswith("SADI_"))
    if env.get("SADI_FAILPOINTS"):
        return warn(
            "failpoints-armed", "SADI_FAILPOINTS is set; faults will be injected", vars=sadi_vars
        )
    return ok("No behaviour-changing environment found", vars=sadi_vars)


@remedy("PLAT-050", "failpoints-armed")
def _plat_050_fp(ctx: Ctx, out: Outcome) -> Fix:
    """Unset SADI_FAILPOINTS."""
    if ctx.os is Os.WINDOWS:
        line = "Remove-Item Env:SADI_FAILPOINTS"
    else:
        line = "unset SADI_FAILPOINTS"
    return Fix(
        "Disarm fault injection",
        (
            action(
                "Remove the variable from this shell; also remove it from your profile or service file.",
                "No output.",
                cmd(ctx.os, line),
                mutates=Mutates.PROCESS,
                changes="Unsets SADI_FAILPOINTS for this shell only.",
            ),
        ),
    )
