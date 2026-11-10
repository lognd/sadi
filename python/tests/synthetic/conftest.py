"""Shared fixtures: an lctt-only app over a tmp data root, real or synthetic."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app


@pytest.fixture(autouse=True)
def _isolate_spill_dirs(isolated_spill_dirs: tuple[Path, Path]) -> None:
    """Apply the shared spill-dir redirect to every test here."""


@pytest.fixture
def make_client(tmp_path: Path) -> Iterator[Callable[..., TestClient]]:
    """Factory `make_client(synthetic=False, root=None)`: a live TestClient, closed after."""
    opened: list[TestClient] = []

    def _make(synthetic: bool = False, root: Path | None = None) -> TestClient:
        labs = LabRegistry()
        assert labs.register(register()).is_ok
        app = create_app(AppSettings(data_root=root or tmp_path, labs=labs, synthetic=synthetic))
        c = TestClient(app)
        c.__enter__()
        opened.append(c)
        return c

    yield _make
    for c in reversed(opened):
        c.__exit__(None, None, None)
