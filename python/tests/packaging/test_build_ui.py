"""build_ui: runs npm steps via an injectable runner and copies dist into the package."""

# frob:ticket 01M6W7RAW944RFCMESYZKJSYXC
from __future__ import annotations

import importlib.util
import sys
import tomllib
from collections.abc import Sequence
from pathlib import Path

import pytest
from typani import Err, Ok, Result

ROOT = Path(__file__).resolve().parents[3]
_spec = importlib.util.spec_from_file_location("build_ui", ROOT / "packaging" / "build_ui.py")
assert _spec is not None and _spec.loader is not None
build_ui_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build_ui_mod)


def _web(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    web.mkdir()
    (web / "package.json").write_text("{}", encoding="utf-8")
    return web


def test_build_copies_dist(tmp_path: Path) -> None:
    """Both npm steps run and dist replaces stale files while keeping .gitkeep."""
    # frob:tests test_build_copies_dist
    web = _web(tmp_path)
    ui = tmp_path / "ui"
    ui.mkdir()
    (ui / ".gitkeep").write_text("", encoding="utf-8")
    (ui / "stale.js").write_text("old", encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: Sequence[str], cwd: Path) -> Result[None, str]:
        calls.append(list(argv))
        assert cwd == web
        if argv[-1] == "build":
            (web / "dist" / "assets").mkdir(parents=True)
            (web / "dist" / "index.html").write_text("<html/>", encoding="utf-8")
            (web / "dist" / "assets" / "a.js").write_text("x", encoding="utf-8")
        return Ok(None)

    got = build_ui_mod.build_ui(web, ui, runner)
    assert got.is_ok
    assert calls == [["npm", "ci"], ["npm", "run", "build"]]
    assert (ui / "index.html").is_file() and (ui / "assets" / "a.js").is_file()
    assert (ui / ".gitkeep").is_file() and not (ui / "stale.js").exists()


def test_build_runner_failure(tmp_path: Path) -> None:
    """A failing npm step returns Err and does not touch the UI dir."""
    # frob:tests test_build_runner_failure
    web = _web(tmp_path)

    def runner(argv: Sequence[str], cwd: Path) -> Result[None, str]:
        return Err("boom")

    got = build_ui_mod.build_ui(web, tmp_path / "ui", runner)
    assert got.is_err and got.danger_err == "boom"
    assert not (tmp_path / "ui").exists()


def test_build_missing_web_and_dist(tmp_path: Path) -> None:
    """Missing package.json or missing index.html in dist yields Err."""
    # frob:tests test_build_missing_web_and_dist
    assert build_ui_mod.build_ui(tmp_path / "nope", tmp_path / "ui").is_err
    web = _web(tmp_path)
    got = build_ui_mod.build_ui(web, tmp_path / "ui", lambda a, c: Ok(None), install=False)
    assert got.is_err


def test_pyproject_ships_ui() -> None:
    """The hatch wheel target includes sadi/_ui/** and the sadi script exists."""
    # frob:tests test_pyproject_ships_ui
    data = tomllib.loads((ROOT / "python" / "pyproject.toml").read_text(encoding="utf-8"))
    wheel = data["tool"]["hatch"]["build"]["targets"]["wheel"]
    assert "sadi/_ui/**" in wheel["artifacts"]
    assert data["project"]["scripts"]["sadi"] == "sadi.launcher:main"
    assert (ROOT / "python" / "sadi" / "_ui" / ".gitkeep").is_file()


def test_run_command_missing_exe(tmp_path: Path) -> None:
    """A command that is not on PATH yields Err rather than raising."""
    # frob:tests test_run_command_missing_exe
    got = build_ui_mod.run_command(["definitely-not-a-real-exe-xyz"], tmp_path)
    assert got.is_err


def test_run_command_success_and_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """run_command maps exit codes to Ok/Err using the current interpreter."""
    # frob:tests test_run_command_success_and_failure
    monkeypatch.setenv("PATH", str(Path(sys.executable).parent))
    py = Path(sys.executable).name
    assert build_ui_mod.run_command([py, "-c", "pass"], tmp_path).is_ok
    assert build_ui_mod.run_command([py, "-c", "raise SystemExit(3)"], tmp_path).is_err
