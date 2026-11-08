"""Tests for the `sadi plugins` CLI."""

# frob:ticket 01M6WFZF75SH31V398E8P7WC5Y
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sadi.cli.plugins import Exit, main
from sadi.plugins.builtin import builtin_source


def run(tmp_path: Path, *args: str) -> int:
    """Invoke the CLI with built-in sources only and an isolated config dir."""
    return main(
        ["--config-dir", str(tmp_path / "cfg"), *args], sources=lambda _settings: [builtin_source()]
    )


def listing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> list[dict[str, object]]:
    """Return `list --json` output."""
    capsys.readouterr()  # drop earlier output
    assert run(tmp_path, "list", "--json") == Exit.OK
    return json.loads(capsys.readouterr().out)


# frob:tests python/sadi/cli/plugins.py::cmd_list
# frob:tests python/sadi/cli/plugins.py::main
# frob:tests python/sadi/cli/plugins.py::build_parser
def test_list_shows_lctt_builtin_enabled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """lctt appears as builtin/enabled in table and JSON."""
    assert run(tmp_path, "list") == Exit.OK
    line = next(ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("lctt"))
    assert "builtin" in line and "enabled" in line
    row = next(r for r in listing(tmp_path, capsys) if r["id"] == "lctt")
    assert row["source"] == "builtin" and row["state"] == "enabled"


# frob:tests python/sadi/cli/plugins.py::cmd_set
def test_disable_then_enable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Disable shows disabled with a restart note; enable restores."""
    assert run(tmp_path, "disable", "lctt") == Exit.OK
    assert "next time SADI starts" in capsys.readouterr().out
    assert next(r for r in listing(tmp_path, capsys) if r["id"] == "lctt")["state"] == "disabled"
    assert run(tmp_path, "enable", "lctt") == Exit.OK
    assert next(r for r in listing(tmp_path, capsys) if r["id"] == "lctt")["state"] == "enabled"


@pytest.mark.parametrize("cmd", ["info", "enable", "disable"])
# frob:tests python/sadi/cli/plugins.py::cmd_set
# frob:tests python/sadi/cli/plugins.py::cmd_info
def test_unknown_id_exit_2_no_traceback(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], cmd: str
) -> None:
    """Unknown ids give a clear one-line error and exit 2."""
    assert run(tmp_path, cmd, "nope") == 2
    err = capsys.readouterr().err
    assert "nope" in err and "lctt" in err and "Traceback" not in err
    assert not (tmp_path / "cfg").exists()


# frob:tests python/sadi/cli/plugins.py::cmd_info
def test_info_shows_details(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """info prints source, state and labs."""
    assert run(tmp_path, "info", "lctt") == Exit.OK
    out = capsys.readouterr().out
    assert "source:   builtin" in out and "sadi.labs.lctt.plugin:register" in out


# frob:tests python/sadi/cli/plugins.py::main
def test_corrupt_state_warns_and_is_preserved(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A damaged state file makes list warn; disable keeps it aside and exits 3."""
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    (cfg / "plugins.json").write_text("garbage")
    assert run(tmp_path, "list") == Exit.OK
    assert "warning" in capsys.readouterr().err
    assert (cfg / "plugins.json").read_text() == "garbage"
    assert run(tmp_path, "disable", "lctt") == Exit.STATE
    assert "corrupt-" in capsys.readouterr().err
    assert list(cfg.glob("plugins.json.corrupt-*"))


# frob:tests python/sadi/cli/plugins.py::default_sources
def test_default_sources_stack(tmp_path: Path) -> None:
    """The default stack is built-in, entry points, local dirs."""
    from sadi.cli.plugins import default_sources
    from sadi.plugins.settings import PluginSettings

    names = [s.name for s in default_sources(PluginSettings(config_dir=tmp_path))]
    assert names == ["builtin", "entry-points", "local-dir"]
