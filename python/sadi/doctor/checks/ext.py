"""EXT checks: the Rust extension sadi_py."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import json
import re
from typing import Any

from typani import Err, Ok, Result

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import (
    CommandRun,
    Layer,
    Mutates,
    Os,
    ProbeError,
    Severity,
    SkipReason,
    Step,
)
from sadi.doctor.steps import action, cmd, manual
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

_ABI_MARKERS = ("PyInit", "GLIBC_", "dlopen", "DLL load failed", "incompatible architecture")
IMPORT_TIMEOUT_S = 20.0
SELFTEST_TIMEOUT_S = 10.0
PORT_ENV = "SADI_PORT"
CHILD_TIMEOUT_S = 10.0

INFO_SCRIPT = (
    "import importlib,json,sadi_py\n"
    "core=importlib.import_module('sadi.core')\n"
    "print(json.dumps({'version':getattr(sadi_py,'__version__',None),"
    "'protocol':getattr(sadi_py,'PROTOCOL_VERSION',None),"
    "'expected_protocol':getattr(core,'PROTOCOL_VERSION',None)}))"
)
VCRUNTIME_SCRIPT = (
    "import ctypes.util,json\n"
    "print(json.dumps([n for n in ('vcruntime140','vcruntime140_1') "
    "if not ctypes.util.find_library(n)]))"
)
FEATURES_SCRIPT = "import json,sadi_py\nprint(json.dumps(list(sadi_py.serial_features())))"
SELFTEST_SCRIPT = "import sadi_py\nsadi_py.selftest()"


def child_json(ctx: Ctx, script: str, timeout: float = CHILD_TIMEOUT_S) -> Result[Any, ProbeError]:
    """Run `python -c script` and parse the last JSON line of its stdout (earlier log lines are ignored); any failure is a ProbeError."""
    res = ctx.probes.run((ctx.probes.python_exe(), "-c", script), timeout)
    if res.is_err:
        return Err(res.unwrap_err())
    run: CommandRun = res.unwrap()
    if run.exit_code != 0:
        return Err(ProbeError(kind="exception", detail=run.stderr_tail[-300:] or "non-zero exit"))
    # frob:ticket 01M6Z2HK9VCDRFZV4Z3WKD8T9Z
    for line in reversed(run.stdout_tail.splitlines()):
        text = line.strip()
        if not text:
            continue
        try:
            return Ok(json.loads(text))
        except ValueError:
            _log.debug("skipping non-JSON child line: %r", text[-80:])
    _log.warning("child output is not JSON: %r", run.stdout_tail[-80:])
    return Err(ProbeError(kind="exception", detail="child output is not JSON"))


@check(
    "EXT-010",
    Layer.EXT,
    "sadi_py imports",
    Severity.BLOCKER,
    {
        "not-installed": "ModuleNotFoundError for sadi_py",
        "abi-mismatch": "The binary exists but does not load on this OS/CPU/Python",
        "crashed": "The import killed the interpreter",
        "timeout": "The import did not finish in 20 s",
    },
    "subprocess `python -c 'import sadi_py'` with a 20 s timeout",
    depends_on=("PY-030",),
)
def ext_010(ctx: Ctx) -> Outcome:
    """Import sadi_py in a child so a native crash cannot take the doctor down."""
    argv = (ctx.probes.python_exe(), "-c", "import sadi_py")
    res = ctx.probes.run(argv, IMPORT_TIMEOUT_S)
    if res.is_err:
        err = res.unwrap_err()
        if err.kind == "timeout":
            return fail("timeout", "Importing sadi_py timed out", detail=err.detail)
        return fail("crashed", f"Could not run the import probe: {err.detail}", detail=err.detail)
    run: CommandRun = res.unwrap()
    if run.exit_code == 0:
        return ok("sadi_py imports", python=argv[0])
    text = run.stderr_tail
    if re.search(r"ModuleNotFoundError.*sadi_py|No module named 'sadi_py'", text):
        return fail("not-installed", "sadi_py is not installed", stderr=text[-300:])
    if "Traceback" not in text:
        return fail(
            "crashed", f"Importing sadi_py exited with code {run.exit_code}", stderr=text[-300:]
        )
    marker = next((m for m in _ABI_MARKERS if m in text), None)
    return fail(
        "abi-mismatch",
        f"sadi_py does not load ({marker or 'ImportError'})",
        marker=marker,
        stderr=text[-300:],
    )


def _build_steps(ctx: Ctx) -> Step:
    """Return the rebuild step shared by the load failures."""
    return action(
        "Rebuild and install the extension for this Python.",
        "maturin finishes with 'Installed sadi_py'.",
        cmd(ctx.os, "uv run maturin develop --release"),
        mutates=Mutates.INSTALL,
        changes="Compiles the Rust crate and installs it into python/.venv.",
        if_not="Install the Rust toolchain from rustup.rs, open a new terminal, and repeat.",
    )


@remedy("EXT-010", "not-installed")
def _ext_010_missing(ctx: Ctx, out: Outcome) -> Fix:
    """Build and install sadi_py."""
    return Fix("Install the Rust extension", (_build_steps(ctx),))


@remedy("EXT-010", "abi-mismatch")
def _ext_010_abi(ctx: Ctx, out: Outcome) -> Fix:
    """Rebuild for this interpreter."""
    clean = action(
        "Remove the stale binary first.",
        "pip reports sadi_py uninstalled (or says it was not installed).",
        cmd(ctx.os, "uv pip uninstall sadi_py"),
        mutates=Mutates.INSTALL,
        changes="Removes the sadi_py package from python/.venv.",
    )
    return Fix("Rebuild the extension for this machine", (clean, _build_steps(ctx)))


@remedy("EXT-010", "crashed")
def _ext_010_crash(ctx: Ctx, out: Outcome) -> Fix:
    """Rebuild after a native crash."""
    return _ext_010_abi(ctx, out)


@remedy("EXT-010", "timeout")
def _ext_010_timeout(ctx: Ctx, out: Outcome) -> Fix:
    """Retry the import by hand."""
    py = "python" if ctx.os is Os.WINDOWS else "python3"
    return Fix(
        "Find out why the import hangs",
        (
            action(
                "Import it by hand and watch for a prompt, antivirus dialog or hang.",
                "The command returns at once with no output.",
                cmd(ctx.os, f"{py} -X importtime -c 'import sadi_py'"),
                if_not="Rebuild with `uv run maturin develop --release` and repeat.",
            ),
        ),
    )


def _unreadable(what: str, err: ProbeError) -> Outcome:
    """Skip a check whose child probe could not produce an answer."""
    reason = SkipReason.TIMEOUT if err.kind == "timeout" else SkipReason.TOOL_MISSING
    return skip(reason, f"Could not read {what} from sadi_py", detail=err.detail)


@check(
    "EXT-020",
    Layer.EXT,
    "sadi_py version matches sadi",
    Severity.BLOCKER,
    {
        "version-mismatch": "sadi_py and sadi report different versions",
        "protocol-mismatch": "sadi_py speaks a different protocol version than sadi expects",
    },
    "child reads sadi_py.__version__ and PROTOCOL_VERSION; compared with the sadi distribution "
    "version and sadi.core.PROTOCOL_VERSION",
    depends_on=("EXT-010",),
)
def ext_020(ctx: Ctx) -> Outcome:
    """Compare the extension's version and protocol with the Python package's."""
    got = child_json(ctx, INFO_SCRIPT)
    if got.is_err:
        return _unreadable("its version", got.unwrap_err())
    info: dict[str, Any] = got.unwrap()
    ext_v = info.get("version")
    py_v = ctx.probes.dist_version("sadi")
    if ext_v is not None and py_v is not None and str(ext_v) != py_v:
        return fail(
            "version-mismatch",
            f"sadi_py is {ext_v} but sadi is {py_v}",
            sadi_py=str(ext_v),
            sadi=py_v,
        )
    want, have = info.get("expected_protocol"), info.get("protocol")
    if want is not None and have is not None and str(want) != str(have):
        return fail(
            "protocol-mismatch",
            f"sadi_py speaks protocol {have} but sadi expects {want}",
            sadi_py=str(have),
            expected=str(want),
        )
    return ok("sadi_py matches sadi", sadi_py=None if ext_v is None else str(ext_v), sadi=py_v)


@remedy("EXT-020", "version-mismatch")
def _ext_020_version(ctx: Ctx, out: Outcome) -> Fix:
    """Rebuild the extension from the same checkout."""
    return Fix("Rebuild sadi_py to match sadi", (_build_steps(ctx),))


@remedy("EXT-020", "protocol-mismatch")
def _ext_020_protocol(ctx: Ctx, out: Outcome) -> Fix:
    """Rebuild after a protocol change."""
    return Fix("Rebuild sadi_py for this protocol version", (_build_steps(ctx),))


@check(
    "EXT-030",
    Layer.EXT,
    "Windows runtime dependencies",
    Severity.BLOCKER,
    {"missing-vcruntime": "vcruntime140.dll or vcruntime140_1.dll cannot be found"},
    "Windows only: ctypes.util.find_library for vcruntime140 and vcruntime140_1",
    applies_to=frozenset({Os.WINDOWS}),
    depends_on=("PY-020",),
)
def ext_030(ctx: Ctx) -> Outcome:
    """Look for the Visual C++ runtime DLLs the extension links against."""
    got = child_json(ctx, VCRUNTIME_SCRIPT)
    if got.is_err:
        return _unreadable("the runtime DLL list", got.unwrap_err())
    missing: list[str] = [str(n) for n in got.unwrap()]
    if missing:
        return fail("missing-vcruntime", f"Missing: {', '.join(missing)}", missing=missing)
    return ok("Visual C++ runtime DLLs found")


@remedy("EXT-030", "missing-vcruntime")
def _ext_030_missing(ctx: Ctx, out: Outcome) -> Fix:
    """Install the Visual C++ redistributable."""
    return Fix(
        "Install the Visual C++ runtime",
        (
            action(
                "Install the Microsoft Visual C++ 2015-2022 x64 redistributable.",
                "winget reports the package installed.",
                cmd(ctx.os, "winget install --id Microsoft.VCRedist.2015+.x64"),
                mutates=Mutates.INSTALL,
                changes="Installs the Visual C++ runtime DLLs system-wide.",
                if_not="Download vc_redist.x64.exe from the Microsoft site and run it.",
            ),
        ),
    )


@check(
    "EXT-040",
    Layer.EXT,
    "Linux udev feature compiled in",
    Severity.WARNING,
    {"no-udev-feature": "sadi_py was built without udev; VID/PID auto-detection is unavailable"},
    "Linux/WSL only: sadi_py.serial_features() must list udev",
    applies_to=frozenset({Os.LINUX, Os.WSL}),
    depends_on=("EXT-010",),
)
def ext_040(ctx: Ctx) -> Outcome:
    """Warn when udev is missing and no explicit port works; an explicit working port is a pass."""
    got = child_json(ctx, FEATURES_SCRIPT)
    if got.is_err:
        return _unreadable("its serial features", got.unwrap_err())
    features = [str(f) for f in got.unwrap()]
    if "udev" in features:
        return ok("sadi_py has udev support", features=features)
    port = explicit_port(ctx)  # frob:ticket 01M6Z5G0SEZ5PNGG11RYBAN6G3
    if port is None:
        _log.info("EXT-040: no udev and no explicit port configured")
        return warn(
            "no-udev-feature",
            "sadi_py has no udev support; use an explicit --port",
            features=features,
        )
    facts = ctx.probes.device_facts(port, 0, False)
    if facts.open_status == "ok" and facts.query_status == "ok":
        _log.info("EXT-040: enumeration unsupported but explicit port %s answers", port)
        return ok(
            f"Enumeration unsupported (no udev); explicit port {port} answers",
            features=features,
            enumeration="unsupported",
            port=port,
        )
    _log.warning("EXT-040: explicit port %s did not answer: %s", port, facts.open_status)
    return warn(
        "no-udev-feature",
        f"sadi_py has no udev support and explicit port {port} did not answer",
        features=features,
        enumeration="unsupported",
        port=port,
        open_status=facts.open_status,
    )


def explicit_port(ctx: Ctx) -> str | None:
    """Return the port named by --port, else SADI_PORT, else None (auto-detect)."""
    return ctx.options.port or ctx.probes.env().get(PORT_ENV) or None


@remedy("EXT-040", "no-udev-feature")
def _ext_040_udev(ctx: Ctx, out: Outcome) -> Fix:
    """Install libudev headers and rebuild."""
    install = (
        "sudo apt install libudev-dev pkg-config"
        if ctx.os in (Os.LINUX, Os.WSL)
        else "brew install pkg-config"
    )
    return Fix(
        "Rebuild sadi_py with udev support",
        (
            action(
                "Install the udev development files.",
                "The package manager finishes without errors.",
                cmd(ctx.os, install),
                mutates=Mutates.INSTALL,
                changes="Installs libudev headers system-wide.",
                if_not="Use your distribution's equivalent of libudev-dev.",
            ),
            _build_steps(ctx),
            manual(
                "Until then, find your board's port (for example `ls -l /dev/ttyUSB*`).",
                "One ttyUSB or ttyACM entry appears when the board is plugged in.",
            ),
            manual(
                "Pass that port explicitly, via --port or the SADI_PORT environment variable.",
                "`sadi-doctor --port <port>` reports the port answers; SADI connects with --port.",
            ),
        ),
    )


@check(
    "EXT-050",
    Layer.EXT,
    "Extension self-test",
    Severity.ERROR,
    {
        "vectors-fail": "The codec disagrees with the committed protocol vectors",
        "timeout": "The self-test did not finish in 10 s",
    },
    "child runs sadi_py.selftest() with a 10 s timeout",
    depends_on=("EXT-010",),
)
def ext_050(ctx: Ctx) -> Outcome:
    """Run the extension's built-in codec and simulator self-test in a child."""
    res = ctx.probes.run((ctx.probes.python_exe(), "-c", SELFTEST_SCRIPT), SELFTEST_TIMEOUT_S)
    if res.is_err:
        err = res.unwrap_err()
        if err.kind == "timeout":
            return fail("timeout", "The sadi_py self-test timed out", detail=err.detail)
        return skip(SkipReason.TOOL_MISSING, "Could not run the self-test", detail=err.detail)
    run: CommandRun = res.unwrap()
    if run.exit_code == 0:
        return ok("sadi_py self-test passed")
    if "AttributeError" in run.stderr_tail:
        return skip(SkipReason.UNVERIFIED, "This sadi_py build has no selftest()")
    return fail(
        "vectors-fail",
        f"sadi_py self-test failed (exit {run.exit_code})",
        stderr=run.stderr_tail[-300:],
    )


@remedy("EXT-050", "vectors-fail")
def _ext_050_vectors(ctx: Ctx, out: Outcome) -> Fix:
    """Rebuild a broken extension."""
    return Fix("Rebuild the extension from a clean build", (_build_steps(ctx),))


@remedy("EXT-050", "timeout")
def _ext_050_timeout(ctx: Ctx, out: Outcome) -> Fix:
    """Retry the self-test by hand."""
    py = "python" if ctx.os is Os.WINDOWS else "python3"
    return Fix(
        "Find out why the self-test hangs",
        (
            action(
                "Run the self-test by hand while the machine is otherwise idle.",
                "The command returns within a second with no output.",
                cmd(ctx.os, f"{py} -c 'import sadi_py; sadi_py.selftest()'"),
                if_not="Rebuild with `uv run maturin develop --release` and repeat.",
            ),
        ),
    )
