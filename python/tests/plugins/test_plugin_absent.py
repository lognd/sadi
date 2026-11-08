"""Core runs with local/private plugins absent; a valid local plugin loads when present."""

# frob:ticket 01M6WFZQ9Y6EBA9WT6VHFMSYPK

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from typani import Ok

from sadi.core.lab import LabId
from sadi.core.registry import LabRegistry
from sadi.plugins import PluginRegistry, PluginState
from sadi.plugins.builtin import builtin_source
from sadi.plugins.local import LocalDirSource, default_dirs
from sadi.plugins.settings import PluginSettings

ROOT = Path(__file__).resolve().parents[3]
PRESENT_ROOT = Path(os.environ.get("SADI_TEST_PRIVATE_ROOT", ROOT))
PKG = "final_project"


def _discover(local: LocalDirSource) -> PluginRegistry:
    """Discover built-in plus the given local source."""
    return PluginRegistry.discover([builtin_source(), local])


# frob:tests python/sadi/plugins/local.py::LocalDirSource.discover
def test_core_runs_with_local_dir_absent(tmp_path: Path) -> None:
    res = LocalDirSource(paths=[tmp_path / "private" / "x" / "plugin"]).discover()
    assert isinstance(res, Ok) and res.value == []
    reg = _discover(LocalDirSource(paths=[tmp_path / "missing"]))
    assert [r.id for r in reg.records()] == ["lctt"]
    assert reg.source_errors() == []
    assert all(r.state is PluginState.ENABLED and not r.errors for r in reg.records())
    labs = LabRegistry.from_plugins(reg)
    assert labs.ids() == [LabId("lctt")]


# frob:tests python/sadi/plugins/local.py::default_dirs
def test_default_dirs_empty_without_private(tmp_path: Path) -> None:
    assert default_dirs(tmp_path) == []
    src = LocalDirSource(root=tmp_path, env={}, settings=PluginSettings(config_dir=tmp_path))
    reg = _discover(src)
    assert [r.id for r in reg.records()] == ["lctt"]


def test_env_path_to_missing_dir_is_harmless(tmp_path: Path) -> None:
    env = {"SADI_PLUGIN_PATH": str(tmp_path / "gone")}
    src = LocalDirSource(env=env, settings=PluginSettings(config_dir=tmp_path))
    reg = _discover(src)
    assert [r.id for r in reg.records()] == ["lctt"]


# frob:tests python/sadi/plugins/local.py::LocalDirSource.discover
def test_valid_local_plugin_loads_from_private_layout(tmp_path: Path) -> None:
    plug = tmp_path / "private" / "demo" / "plugin"
    plug.mkdir(parents=True)
    (plug / "sadi_plugin.toml").write_text(
        'id = "demo"\nversion = "1.0.0"\napi_version = ">=1.0,<2"\n'
        '[contributions]\nlabs = ["lab:make"]\n'
    )
    (plug / "lab.py").write_text(
        "from tests.core.test_lab_registry import FakeLab\n"
        "def make():\n    return FakeLab('demo_lab')\n"
    )
    src = LocalDirSource(root=tmp_path, env={}, settings=PluginSettings(config_dir=tmp_path))
    reg = _discover(src)
    rec = reg.get("demo")
    assert rec is not None and rec.state is PluginState.ENABLED
    assert [lab.id for lab in rec.labs] == [LabId("demo_lab")]
    assert reg.get("lctt") is not None


def _tracked_python_files() -> list[Path]:
    """Python files of the repo that are tracked (everything under python/ except venvs)."""
    skip = {".venv", "__pycache__", "node_modules"}
    return [p for p in (ROOT / "python").rglob("*.py") if not skip & set(p.parts)]


def _imported_modules(path: Path) -> list[str]:
    """Absolute module names imported by a source file."""
    mods: list[str] = []
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            mods += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and not node.level:
            mods.append(node.module or "")
    return mods


def test_no_tracked_file_imports_private_plugin() -> None:
    files = _tracked_python_files()
    assert files
    bad = [
        f"{p.relative_to(ROOT)}: {m}"
        for p in files
        for m in _imported_modules(p)
        if PKG in m.split(".") or m.split(".")[0] in {"private", "plugins"}
    ]
    assert bad == []


@pytest.mark.skipif(not default_dirs(PRESENT_ROOT), reason="no local plugin dirs in this checkout")
def test_present_local_plugins_load_enabled() -> None:
    reg = _discover(
        LocalDirSource(root=PRESENT_ROOT, env={}, settings=PluginSettings(config_dir=ROOT))
    )
    local = [r for r in reg.records() if r.source != "builtin"]
    assert local
    assert all(r.state is PluginState.ENABLED for r in local), [r.errors for r in local]
