"""The launcher enables the synthetic source only with the flag AND the typed phrase."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from sadi import launcher
from sadi.synthetic.provenance import CONFIRM_PHRASE

BASE = ["serve", "--no-browser", "--skip-preflight", "--port", "0"]


def _run(tmp_path: Path, extra: list[str]) -> tuple[int, list[Any]]:
    seen: list[Any] = []

    def _serve(app: Any, host: str, port: int) -> None:
        seen.append(app)

    code = launcher.main([*BASE, "--data-root", str(tmp_path), *extra], _serve)
    return code, seen


# frob:tests python/sadi/launcher.py::_resolve_synthetic
@pytest.mark.parametrize(
    "extra",
    [
        ["--synthetic-specimen"],
        ["--synthetic-specimen", "--i-understand-this-is-fake=yes"],
        ["--i-understand-this-is-fake=" + CONFIRM_PHRASE],
    ],
)
def test_refused_without_flag_and_exact_phrase(
    tmp_path: Path, extra: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing flag, missing phrase or a wrong phrase exit with usage and serve nothing."""
    code, seen = _run(tmp_path, extra)
    assert code == launcher.EXIT_USAGE and not seen
    assert "sadi:" in capsys.readouterr().err


# frob:tests python/sadi/launcher.py::_resolve_synthetic
def test_env_alone_never_enables(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Environment variables cannot turn the synthetic source on."""
    for name in ("SADI_SYNTHETIC", "SADI_SYNTHETIC_SPECIMEN", "SADI_I_UNDERSTAND_THIS_IS_FAKE"):
        monkeypatch.setenv(name, CONFIRM_PHRASE)
    code, seen = _run(tmp_path, [])
    assert code == 0
    assert seen[0].state.sessions.provenance().synthetic is False


# frob:tests python/sadi/launcher.py::_serve
def test_not_combinable_with_sim(tmp_path: Path) -> None:
    """--synthetic-specimen with --sim is a usage error."""
    extra = ["--synthetic-specimen", f"--i-understand-this-is-fake={CONFIRM_PHRASE}", "--sim"]
    code, seen = _run(tmp_path, extra)
    assert code == launcher.EXIT_USAGE and not seen


# frob:tests python/sadi/launcher.py::_open_synthetic
def test_flag_and_phrase_enable_with_banner(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Flag plus phrase serves a synthetic app and prints the loud banner."""
    extra = ["--synthetic-specimen", f"--i-understand-this-is-fake={CONFIRM_PHRASE}"]
    code, seen = _run(tmp_path, extra)
    assert code == 0 and len(seen) == 1
    assert seen[0].state.sessions.provenance().synthetic is True
    assert "SYNTHETIC SPECIMEN" in capsys.readouterr().out
