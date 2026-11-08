"""PLAT checks: OS, locale and environment."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import re

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity, SkipReason
from sadi.doctor.steps import action, cmd, manual

_MIN_MACOS = 12
_MIN_WINDOWS = 10
_PATH_LIMIT = 200
_SESSION_PATH_RESERVE = 100
_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)
_ARCH_ALIASES = {
    "x86_64": "x64",
    "amd64": "x64",
    "x64": "x64",
    "arm64": "arm64",
    "aarch64": "arm64",
}


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


def _arch(text: str) -> str | None:
    """Normalise an architecture or target-triple string to x64, arm64 or None."""
    low = text.lower()
    for alias, norm in _ARCH_ALIASES.items():
        if alias in low:
            return norm
    return None


@check(
    "PLAT-020",
    Layer.PLAT,
    "CPU architecture matches the installed wheel",
    Severity.BLOCKER,
    {
        "arch-mismatch": "The interpreter's architecture differs from the sadi_py build target",
        "unknown-arch": "The CPU architecture is not x86_64 or arm64",
    },
    "platform.machine() vs sadi_py.BUILD_TARGET; macOS Rosetta via sysctl.proc_translated",
)  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
def plat_020(ctx: Ctx) -> Outcome:
    """Fail when the native extension was built for another architecture."""
    machine = ctx.probes.machine()
    arch = _arch(machine)
    if arch is None:
        return fail("unknown-arch", f"Unsupported CPU architecture {machine}", machine=machine)
    target = ctx.probes.build_target()
    if target is None:
        return skip(SkipReason.UNVERIFIED, "sadi_py records no build target", machine=machine)
    built = _arch(target)
    if built is not None and built != arch:
        return fail(
            "arch-mismatch",
            f"Python runs as {machine} but sadi_py was built for {target}",
            machine=machine,
            target=target,
        )
    return ok(f"{machine} matches the sadi_py build", machine=machine, target=target)


@remedy("PLAT-020", "arch-mismatch")
def _plat_020_mismatch(ctx: Ctx, out: Outcome) -> Fix:  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    """Reinstall with a matching interpreter."""
    return Fix(
        "Use a Python that matches the installed wheel",
        (
            manual(
                "Install a Python built for this CPU (on Apple silicon use the arm64 build, not "
                "the Rosetta x86_64 one), then recreate the virtual environment.",
                '`python -c "import platform; print(platform.machine())"` prints the native arch.',
                if_not="Install SADI from a wheel built for the architecture Python reports.",
            ),
        ),
    )


@remedy("PLAT-020", "unknown-arch")
def _plat_020_unknown(ctx: Ctx, out: Outcome) -> Fix:  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    """Tell the user SADI ships no wheel for this CPU."""
    return Fix(
        "Run SADI on a supported CPU",
        (
            manual(
                "SADI ships wheels for x86_64 and arm64 only; use such a machine.",
                '`python -c "import platform; print(platform.machine())"` prints x86_64 or arm64.',
                if_not="Build sadi_py from source for this CPU.",
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
    if bool(env.get("SADI_FAILPOINTS")):
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


def _bad_components(root: str) -> tuple[list[str], list[str]]:
    """Return (reserved-name components, trailing dot or space components) of a path."""
    reserved: list[str] = []
    trailing: list[str] = []
    for part in re.split(r"[\\/]", root):
        if part in ("", ".", "..") or re.fullmatch(r"[A-Za-z]:", part):
            continue
        if part.split(".", 1)[0].upper() in _RESERVED:
            reserved.append(part)
        if part.endswith((".", " ")):
            trailing.append(part)
    return reserved, trailing


@check(
    "PLAT-040",
    Layer.PLAT,
    "Windows long paths and reserved names",
    Severity.WARNING,
    {
        "long-paths-off": "Long paths are disabled and the data root leaves little room",
        "reserved-name-in-path": "A data root component is a reserved device name",
        "trailing-dot-or-space": "A data root component ends with a dot or a space",
    },
    "HKLM LongPathsEnabled; data root length; components vs CON PRN AUX NUL COM1-9 LPT1-9",
    applies_to=frozenset({Os.WINDOWS}),
)  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
def plat_040(ctx: Ctx) -> Outcome:
    """Warn about Windows path rules that break session files under the data root."""
    root = ctx.data_root or ctx.probes.user_data_dir()
    reserved, trailing = _bad_components(root)
    if reserved:
        return warn("reserved-name-in-path", f"{root} contains {reserved[0]}", root=root)
    if trailing:
        return warn(
            "trailing-dot-or-space", f"{root} has a component ending in '.' or ' '", root=root
        )
    longest = len(root) + _SESSION_PATH_RESERVE
    if longest > _PATH_LIMIT and ctx.probes.long_paths_enabled() is False:
        return warn(
            "long-paths-off",
            f"Session paths under {root} may pass {_PATH_LIMIT} characters",
            root=root,
            estimated_longest=longest,
        )
    return ok("Data root path is portable on Windows", root=root)


@remedy("PLAT-040", "long-paths-off")
def _plat_040_long(ctx: Ctx, out: Outcome) -> Fix:  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    """Enable long paths or move the root."""
    return Fix(
        "Enable Windows long paths",
        (
            action(
                "In an elevated PowerShell, enable long paths, then sign out and in.",
                "No output.",
                cmd(
                    Os.WINDOWS,
                    "Set-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\FileSystem' "
                    "LongPathsEnabled 1",
                ),
                mutates=Mutates.SYSTEM,
                changes="Sets the LongPathsEnabled registry value to 1.",
                if_not="Or choose a shorter data root with --data-root.",
            ),
        ),
    )


@remedy("PLAT-040", "reserved-name-in-path")
def _plat_040_reserved(ctx: Ctx, out: Outcome) -> Fix:  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    """Move the root off reserved names."""
    return Fix(
        "Choose a data root without reserved names",
        (
            manual(
                "Pick a data root whose folders are not CON, PRN, AUX, NUL, COM1-9 or LPT1-9.",
                "The new path contains none of those names.",
                if_not="Use a plain path such as C:\\SADI-data.",
            ),
        ),
    )


@remedy("PLAT-040", "trailing-dot-or-space")
def _plat_040_trailing(ctx: Ctx, out: Outcome) -> Fix:  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    """Rename the folder without trailing dot or space."""
    return Fix(
        "Rename folders that end with a dot or space",
        (
            manual(
                "Rename or choose a data root whose folders do not end with '.' or a space.",
                "No component of the path ends with '.' or a space.",
                if_not="Use a plain path such as C:\\SADI-data.",
            ),
        ),
    )
