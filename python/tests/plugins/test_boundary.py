"""Plugins may import only core public API and sadi.plugins; never store or job internals."""

# frob:ticket 01M6WFZ1N70HDJJRZWRHWP4E7Y

from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SADI = ROOT / "python" / "sadi"
ALLOWED = ("sadi.core", "sadi.uncertainty", "sadi.logging_setup")
FORBIDDEN = ("sadi.store", "sadi.jobs")
BUILTIN_PLUGIN_DIRS = [SADI / "labs" / "lctt"]


def _local_dirs() -> list[Path]:
    """Local plugin dirs present in the checkout (all gitignored, may be absent)."""
    found = [p for p in (ROOT / "plugins",) if p.is_dir()]
    private = ROOT / "private"
    if private.is_dir():
        found += [p for p in sorted(private.glob("*/plugin")) if p.is_dir()]
    return found


def _under(mod: str, prefix: str) -> bool:
    """True when `mod` is `prefix` or one of its submodules."""
    return mod == prefix or mod.startswith(prefix + ".")


def violations(source: str, own: str | None) -> list[str]:
    """Return imported sadi modules a plugin (own package `own`) may not import."""
    bad: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            mods = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                continue
            mods = [node.module or ""]
        else:
            continue
        for mod in mods:
            if not _under(mod, "sadi"):
                continue
            public = all(not p.startswith("_") for p in mod.split("."))
            ok = (
                public
                and not any(_under(mod, f) for f in FORBIDDEN)
                and (
                    mod == "sadi.plugins"
                    or (own is not None and _under(mod, own))
                    or any(_under(mod, a) for a in ALLOWED)
                )
            )
            if not ok:
                bad.append(mod)
    return bad


def _own(pkg_dir: Path) -> str | None:
    """Dotted package name for a built-in plugin dir, None for local dirs."""
    try:
        return ".".join(pkg_dir.relative_to(SADI.parent).parts)
    except ValueError:
        return None


@pytest.mark.parametrize("pkg_dir", [*BUILTIN_PLUGIN_DIRS, *_local_dirs()], ids=str)
def test_plugin_imports_within_boundary(pkg_dir: Path) -> None:
    own = _own(pkg_dir)
    offenders = {
        str(p): bad
        for p in pkg_dir.rglob("*.py")
        if (bad := violations(p.read_text(encoding="utf-8"), own))
    }
    assert offenders == {}


@pytest.mark.parametrize(
    "src",
    [
        "import sadi.store.wal",
        "from sadi.store.wal import Wal",
        "from sadi.store import session",
        "from sadi.jobs.runner import run",
        "import sadi.jobs",
        "from sadi.core._private import x",
        "from sadi.plugins.registry import PluginRegistry",
    ],
)
def test_fixture_plugin_violations_flagged(src: str) -> None:
    assert violations(src, "sadi.labs.fixture") != []


def test_allowed_imports_pass() -> None:
    ok = (
        "from sadi.core.lab import LabModule\nfrom sadi.plugins import PluginManifest\nimport numpy"
    )
    assert violations(ok, "sadi.labs.fixture") == []
