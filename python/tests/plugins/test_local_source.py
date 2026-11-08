"""Tests for LocalDirSource and PluginSettings."""

# frob:ticket 01M6WFZ1R6ATYWRVW3315G6CCX

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from typani import Ok

from sadi.plugins import PluginRegistry, PluginState
from sadi.plugins.local import LocalDirSource
from sadi.plugins.settings import PluginSettings

MANIFEST = """id = "{pid}"
version = "1.0.0"
api_version = ">=1.0,<2"
[contributions]
labs = {labs}
"""

LAB_SRC = """
from tests.core.test_lab_registry import FakeLab

def make():
    return FakeLab("{lid}")
"""


def _plugin(root: Path, pid: str, lid: str | None = None) -> None:
    d = root / pid
    d.mkdir(parents=True)
    labs = '["labmod:make"]' if lid is not None else "[]"
    (d / "sadi_plugin.toml").write_text(MANIFEST.format(pid=pid, labs=labs))
    if lid is not None:
        (d / "labmod.py").write_text(LAB_SRC.format(lid=lid))


# frob:tests python/sadi/plugins/local.py::LocalDirSource.discover
# frob:tests python/sadi/plugins/local.py::LocalDirSource.__init__
def test_loads_without_install(tmp_path: Path) -> None:
    _plugin(tmp_path, "alpha", "alpha_lab")
    res = LocalDirSource(paths=[tmp_path]).discover()
    assert isinstance(res, Ok)
    reg = PluginRegistry.discover([LocalDirSource(paths=[tmp_path])])
    rec = reg.get("alpha")
    assert rec is not None and rec.state == PluginState.ENABLED
    assert len(rec.labs) == 1


def test_absent_dirs_ok(tmp_path: Path) -> None:
    res = LocalDirSource(paths=[tmp_path / "nope"]).discover()
    assert isinstance(res, Ok) and res.value == []
    res = LocalDirSource(
        root=tmp_path, env={}, settings=PluginSettings(config_dir=tmp_path)
    ).discover()
    assert isinstance(res, Ok) and res.value == []


def test_broken_plugin_isolated(tmp_path: Path) -> None:
    _plugin(tmp_path, "good", "good_lab")
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "sadi_plugin.toml").write_text("not = [toml")
    (tmp_path / "boom").mkdir()
    (tmp_path / "boom" / "sadi_plugin.toml").write_text(MANIFEST.format(pid="boom", labs="[]"))
    (tmp_path / "boom" / "__init__.py").write_text("raise RuntimeError('x')")
    res = LocalDirSource(paths=[tmp_path]).discover()
    assert isinstance(res, Ok)
    by = {c.name: c for c in res.value}
    assert by["good"].manifest is not None
    assert by["bad"].issues and by["boom"].issues
    reg = PluginRegistry.discover([LocalDirSource(paths=[tmp_path])])
    good = reg.get("good")
    assert good is not None
    assert good.state == PluginState.ENABLED


# frob:tests python/sadi/plugins/settings.py::PluginSettings.effective_paths
# frob:tests python/sadi/plugins/settings.py::default_config_dir
def test_env_path_wins(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    _plugin(a, "pa")
    _plugin(b, "pb")
    assert PluginSettings().config_dir.name == "sadi"
    settings = PluginSettings(plugin_paths=(a,), config_dir=tmp_path)
    assert settings.effective_paths({}) == (a,)
    env = {"SADI_PLUGIN_PATH": f"{b}{os.pathsep}{tmp_path / 'zz'}"}
    res = LocalDirSource(settings=settings, env=env).discover()
    assert isinstance(res, Ok) and [c.name for c in res.value] == ["pb"]


# frob:tests python/sadi/plugins/local.py::default_dirs
def test_default_dirs(tmp_path: Path) -> None:
    _plugin(tmp_path / "plugins", "p1")
    _plugin(tmp_path / "private" / "x" / "plugin", "p2")
    res = LocalDirSource(
        root=tmp_path, env={}, settings=PluginSettings(config_dir=tmp_path)
    ).discover()
    assert isinstance(res, Ok) and sorted(c.name for c in res.value) == ["p1", "p2"]


def test_plugins_dir_gitignored() -> None:
    repo = Path(__file__).resolve().parents[3]
    r = subprocess.run(["git", "check-ignore", "plugins/x"], cwd=repo, capture_output=True)
    assert r.returncode == 0
