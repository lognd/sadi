"""Tests for the FastAPI app factory."""

# frob:ticket 01M6WKQCC4HJ5C8HXP946BRKXW

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sadi.plugins import PluginRegistry
from sadi.plugins.builtin import builtin_source
from sadi.server.app import AppSettings, create_app


def _client() -> TestClient:
    reg = PluginRegistry.discover([builtin_source()])
    return TestClient(create_app(AppSettings(registry=reg, data_root=Path("x"))))


def test_plugins_route_reachable() -> None:
    """GET /api/plugins is served through create_app."""
    res = _client().get("/api/plugins")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_doctor_route_reachable() -> None:
    """POST of an unknown doctor check id is routed and answers 404 from the doctor router."""
    res = _client().post("/api/doctor/no-such-check/run")
    assert res.status_code == 404
    assert "detail" in res.json()


def test_unknown_route_404() -> None:
    """An unmounted path returns 404."""
    assert _client().get("/api/nope").status_code == 404


def test_settings_injected_and_no_shared_state() -> None:
    """Each app carries its own settings."""
    a = create_app(AppSettings(data_root=Path("a")))
    b = create_app(AppSettings(data_root=Path("b")))
    assert a.state.settings.data_root == Path("a")
    assert b.state.settings.data_root == Path("b")
