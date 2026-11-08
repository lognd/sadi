"""PY checks: interpreter, package and dependency health."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from packaging.specifiers import InvalidSpecifier, SpecifierSet

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity
from sadi.doctor.steps import action, cmd, manual

HARD_DEPS: dict[str, str] = {
    "pydantic": "pydantic",
    "typani": "typani",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "numpy": "numpy",
    "crc32c": "crc32c",
}


@check(
    "PY-010",
    Layer.PY,
    "Python interpreter version",
    Severity.BLOCKER,
    {
        "too-old": "Interpreter older than the sadi requires-python bound",
    },
    "sys.version_info vs Requires-Python of the installed sadi distribution",
)
def py_010(ctx: Ctx) -> Outcome:
    """Compare the interpreter with the package's Requires-Python."""
    major, minor, micro = ctx.probes.py_version()
    version = f"{major}.{minor}.{micro}"
    spec_text = ctx.probes.requires_python("sadi") or ">=3.11"
    try:
        spec = SpecifierSet(spec_text)
    except InvalidSpecifier:
        spec = SpecifierSet(">=3.11")
    if version not in spec:
        return fail(
            "too-old",
            f"Python {version} does not satisfy {spec_text}",
            python=version,
            required=spec_text,
        )
    return ok(f"Python {version} satisfies {spec_text}", python=version, required=spec_text)


@remedy("PY-010", "too-old")
def _py_010_old(ctx: Ctx, out: Outcome) -> Fix:
    """Install a newer Python through uv."""
    return Fix(
        "Use a newer Python",
        (
            action(
                "Install a supported Python with uv.",
                "uv reports an installed CPython 3.12 or newer.",
                cmd(ctx.os, "uv python install 3.12"),
                mutates=Mutates.INSTALL,
                changes="Downloads a Python into uv's managed directory; the system Python is untouched.",
                if_not="Install uv first (see PY-040), or install Python from python.org.",
            ),
            action(
                "Recreate the project environment with it.",
                "uv finishes syncing without errors.",
                cmd(ctx.os, "uv sync --python 3.12"),
                mutates=Mutates.INSTALL,
                changes="Rebuilds the project virtual environment.",
            ),
        ),
    )


@check(
    "PY-020",
    Layer.PY,
    "sadi package installed",
    Severity.BLOCKER,
    {"not-installed": "No sadi distribution metadata found"},
    "importlib.metadata.version('sadi')",
    depends_on=("PY-010",),
)
def py_020(ctx: Ctx) -> Outcome:
    """Confirm the sadi distribution is installed."""
    version = ctx.probes.dist_version("sadi")
    if version is None:
        return fail("not-installed", "The sadi package is not installed in this Python")
    return ok(f"sadi {version} is installed", sadi_version=version)


@remedy("PY-020", "not-installed")
def _py_020_missing(ctx: Ctx, out: Outcome) -> Fix:
    """Install the project."""
    return Fix(
        "Install SADI into this environment",
        (
            action(
                "From the repository's python/ directory, install the project.",
                "uv finishes syncing without errors.",
                cmd(ctx.os, "uv sync"),
                mutates=Mutates.INSTALL,
                changes="Creates or updates python/.venv with SADI and its dependencies.",
                if_not="Check you are in the python/ directory that holds pyproject.toml.",
            ),
        ),
    )


@check(
    "PY-030",
    Layer.PY,
    "Required dependencies importable",
    Severity.BLOCKER,
    {
        "missing": "A required distribution is not installed",
        "import-error": "A dependency is installed but fails to import",
        "pydantic-v1": "pydantic 1.x is installed; SADI needs 2.x",
    },
    "importlib.metadata.version then import of each hard dependency",
    depends_on=("PY-020",),
)
def py_030(ctx: Ctx) -> Outcome:
    """Check every hard dependency installs and imports."""
    missing = [d for d in HARD_DEPS if ctx.probes.dist_version(d) is None]
    if missing:
        return fail("missing", f"Missing: {', '.join(missing)}", missing=missing)
    pyd = ctx.probes.dist_version("pydantic") or ""
    if pyd.startswith("1."):
        return fail("pydantic-v1", f"pydantic {pyd} is installed", pydantic=pyd)
    broken = {
        d: err for d, m in HARD_DEPS.items() if (err := ctx.probes.import_error(m)) is not None
    }
    if broken:
        first = next(iter(broken))
        return fail(
            "import-error",
            f"{first} fails to import: {broken[first]}",
            broken=[f"{k}: {v}" for k, v in broken.items()],
        )
    return ok(f"{len(HARD_DEPS)} required dependencies import", checked=list(HARD_DEPS))


@remedy("PY-030", "missing")
def _py_030_missing(ctx: Ctx, out: Outcome) -> Fix:
    """Reinstall dependencies."""
    names = ", ".join(str(n) for n in out.facts.get("missing", []) or [])
    return Fix(
        f"Install the missing packages ({names})",
        (
            action(
                "Sync the environment from the lock file.",
                "uv finishes syncing without errors.",
                cmd(ctx.os, "uv sync"),
                mutates=Mutates.INSTALL,
                changes="Installs the missing packages into python/.venv.",
                if_not="Read the error; a network failure needs the network, then repeat.",
            ),
        ),
    )


@remedy("PY-030", "import-error")
def _py_030_import(ctx: Ctx, out: Outcome) -> Fix:
    """Reinstall a broken dependency."""
    return Fix(
        "Reinstall the broken dependency",
        (
            action(
                "Force a clean reinstall of the environment packages.",
                "uv finishes without errors.",
                cmd(ctx.os, "uv sync --reinstall"),
                mutates=Mutates.INSTALL,
                changes="Reinstalls every package in python/.venv.",
                if_not="Send the 'broken' lines from `sadi-doctor --json` to the maintainers.",
            ),
        ),
    )


@remedy("PY-030", "pydantic-v1")
def _py_030_v1(ctx: Ctx, out: Outcome) -> Fix:
    """Upgrade pydantic."""
    return Fix(
        "Upgrade pydantic to 2.x",
        (
            action(
                "Sync the project, which pins pydantic 2.",
                "uv finishes syncing without errors.",
                cmd(ctx.os, "uv sync --reinstall-package pydantic"),
                mutates=Mutates.INSTALL,
                changes="Reinstalls pydantic in python/.venv.",
            ),
        ),
    )


@check(
    "PY-040",
    Layer.PY,
    "uv available",
    Severity.WARNING,
    {"uv-missing": "uv is not on PATH"},
    "shutil.which('uv')",
)
def py_040(ctx: Ctx) -> Outcome:
    """Warn when uv is absent (developer layouts need it)."""
    path = ctx.probes.which("uv")
    if path is None:
        return warn("uv-missing", "uv is not on PATH", path=None)
    return ok(f"uv found at {path}", path=path)


@remedy("PY-040", "uv-missing")
def _py_040_missing(ctx: Ctx, out: Outcome) -> Fix:
    """Install uv."""
    if ctx.os is Os.WINDOWS:
        install = cmd(
            ctx.os,
            'powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"',
        )
    else:
        install = cmd(ctx.os, "curl -LsSf https://astral.sh/uv/install.sh | sh")
    return Fix(
        "Install uv",
        (
            action(
                "Run the official uv installer.",
                "The installer prints where uv was installed.",
                install,
                mutates=Mutates.INSTALL,
                changes="Installs the uv binary into your user directory.",
                if_not="Download uv manually from the astral.sh/uv page.",
            ),
            manual(
                "Open a new terminal so PATH picks up uv.",
                "`uv --version` prints a version.",
            ),
        ),
    )


def _norm(path: str, os: Os) -> str:
    """Normalise a path for comparison: forward slashes, no trailing slash, folded on Windows."""
    text = path.replace("\\", "/").rstrip("/")
    return text.casefold() if os is Os.WINDOWS else text


@check(
    "PY-050",
    Layer.PY,
    "Virtual environment is the one SADI was installed into",
    Severity.WARNING,
    {
        "wrong-venv": "A different virtual environment is active than the running interpreter's",
        "system-python": "SADI runs in the system interpreter, not a virtual environment",
    },
    "interpreter location and pyvenv.cfg vs the VIRTUAL_ENV environment variable",
    depends_on=("PY-020",),
)
def py_050(ctx: Ctx) -> Outcome:
    """Compare the interpreter's environment with the one the shell has activated."""
    exe = _norm(ctx.probes.python_exe(), ctx.os)
    prefix = exe.rsplit("/", 2)[0] if exe.count("/") >= 2 else ""
    active = ctx.probes.env().get("VIRTUAL_ENV")
    if active and _norm(active, ctx.os) != prefix:
        return warn(
            "wrong-venv",
            f"VIRTUAL_ENV is {active} but SADI runs from {prefix or exe}",
            active=active,
            interpreter=exe,
        )
    if not prefix or not ctx.probes.exists(f"{prefix}/pyvenv.cfg"):
        return warn("system-python", f"SADI runs in the system interpreter {exe}", interpreter=exe)
    return ok(f"SADI runs in the virtual environment {prefix}", venv=prefix)


@remedy("PY-050", "wrong-venv")
def _py_050_wrong(ctx: Ctx, out: Outcome) -> Fix:
    """Deactivate the stray environment."""
    leave = "deactivate"
    return Fix(
        "Use the environment SADI lives in",
        (
            action(
                "Leave the active environment.",
                "Your prompt no longer shows an environment name.",
                cmd(ctx.os, leave),
                if_not="Open a new terminal.",
            ),
            action(
                "Start SADI through uv, which picks the project environment.",
                "uv starts SADI without a mismatch warning.",
                cmd(ctx.os, "uv run sadi-doctor"),
            ),
        ),
    )


@remedy("PY-050", "system-python")
def _py_050_system(ctx: Ctx, out: Outcome) -> Fix:
    """Move into a project environment."""
    return Fix(
        "Install SADI into a virtual environment",
        (
            action(
                "From the python/ directory, create the project environment.",
                "uv finishes syncing without errors.",
                cmd(ctx.os, "uv sync"),
                mutates=Mutates.INSTALL,
                changes="Creates python/.venv with SADI and its dependencies.",
            ),
            action(
                "Run the doctor through it.",
                "The doctor starts without errors.",
                cmd(ctx.os, "uv run sadi-doctor"),
            ),
        ),
    )


MAX_LISTED = 10


@check(
    "PY-060",
    Layer.PY,
    "Package integrity",
    Severity.WARNING,
    {
        "modified-files": "Installed files differ from the hashes recorded at install time",
        "missing-files": "Files recorded at install time are gone",
    },
    "sha256 of sampled RECORD entries: sadi/doctor, sadi/store and sadi/web/dist/index.html",
    depends_on=("PY-020",),
)
def py_060(ctx: Ctx) -> Outcome:
    """Compare sampled installed files with their recorded hashes (read-only)."""
    modified, missing = ctx.probes.package_integrity()
    if missing:
        return fail(
            "missing-files",
            f"{len(missing)} installed file(s) are missing, e.g. {missing[0]}",
            missing=missing[:MAX_LISTED],
        )
    if modified:
        return warn(
            "modified-files",
            f"{len(modified)} installed file(s) were modified, e.g. {modified[0]}",
            modified=modified[:MAX_LISTED],
        )
    return ok("Sampled package files match their recorded hashes")


@remedy("PY-060", "modified-files")
def _py_060_modified(ctx: Ctx, out: Outcome) -> Fix:
    """Reinstall the package to restore pristine files."""
    return Fix(
        "Restore the modified files",
        (
            action(
                "Reinstall SADI so the files match the release.",
                "uv finishes without errors.",
                cmd(ctx.os, "uv sync --reinstall-package sadi"),
                mutates=Mutates.INSTALL,
                changes="Replaces the installed SADI files, discarding local edits to them.",
                if_not="If you edit SADI on purpose, ignore this warning.",
            ),
        ),
    )


@remedy("PY-060", "missing-files")
def _py_060_missing(ctx: Ctx, out: Outcome) -> Fix:
    """Reinstall to restore deleted files."""
    return _py_060_modified(ctx, out)
