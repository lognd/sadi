"""EXT checks: the Rust extension sadi_py."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import re

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy
from sadi.doctor.schema import CommandRun, Layer, Mutates, Os, Severity, Step
from sadi.doctor.steps import action, cmd

_ABI_MARKERS = ("PyInit", "GLIBC_", "dlopen", "DLL load failed", "incompatible architecture")
IMPORT_TIMEOUT_S = 20.0


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
