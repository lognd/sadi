"""Launcher UI resolution: explicit, packaged sadi/_ui, then web/dist."""

# frob:ticket 01M6W7RAW944RFCMESYZKJSYXC
from __future__ import annotations

from pathlib import Path

import pytest

from sadi import launcher
from sadi.webdist import CHECKOUT_WEB_DIST


def test_explicit_wins(tmp_path: Path) -> None:
    """An explicit path is returned untouched."""
    # frob:tests test_explicit_wins
    assert launcher.resolve_web_dist(tmp_path) == tmp_path


def test_packaged_preferred(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A packaged _ui with index.html beats the web/dist fallback."""
    # frob:tests test_packaged_preferred
    pkg = tmp_path / "sadi"
    (pkg / "_ui").mkdir(parents=True)
    (pkg / "_ui" / "index.html").write_text("<html/>", encoding="utf-8")
    monkeypatch.setattr(launcher.resources, "files", lambda _name: pkg)
    assert launcher.resolve_web_dist(None) == pkg / "_ui"


def test_fallback_to_web_dist(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without a packaged index.html the resolver falls back to web/dist."""
    # frob:tests test_fallback_to_web_dist
    (tmp_path / "_ui").mkdir()
    monkeypatch.setattr(launcher.resources, "files", lambda _name: tmp_path)
    assert launcher.resolve_web_dist(None) == launcher.DEFAULT_WEB_DIST


def test_fallback_independent_of_cwd(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The checkout fallback is absolute, so a different cwd cannot break it."""
    # frob:tests test_fallback_independent_of_cwd
    (tmp_path / "_ui").mkdir()
    monkeypatch.setattr(launcher.resources, "files", lambda _name: tmp_path)
    monkeypatch.chdir(tmp_path)
    got = launcher.resolve_web_dist(None)
    assert got.is_absolute()
    assert got == CHECKOUT_WEB_DIST
    assert got.parts[-2:] == ("web", "dist")
