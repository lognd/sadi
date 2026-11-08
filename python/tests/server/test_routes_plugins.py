"""Tests for the plugin status routes (handlers called directly; no HTTP client installed)."""

# frob:ticket 01M6WFZF9FD9QNXP62MCETRNEA

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.routing import APIRoute

from sadi.plugins import PluginRegistry
from sadi.plugins.builtin import builtin_source
from sadi.plugins.sources import BuiltinSource
from sadi.server.routes_plugins import make_plugins_router


def _routes(router: APIRouter) -> list[APIRoute]:
    return [r for r in router.routes if isinstance(r, APIRoute)]


def _endpoint(router: APIRouter, path: str) -> Callable[..., Any]:
    return next(r.endpoint for r in _routes(router) if r.path == path)


def _router() -> APIRouter:
    reg = PluginRegistry.discover([builtin_source(), BuiltinSource([{"bogus": 1}])])
    return make_plugins_router(reg)


# frob:tests python/sadi/server/routes_plugins.py::make_plugins_router
def test_paths_registered() -> None:
    paths = {r.path for r in _routes(_router())}
    assert paths == {"/api/plugins", "/api/plugins/{plugin_id}"}


# frob:tests python/sadi/server/routes_plugins.py::make_plugins_router
def test_list_includes_enabled_and_failed() -> None:
    items = _endpoint(_router(), "/api/plugins")()
    states = {i.id: i.state.value for i in items}
    assert states["lctt"] == "enabled"
    assert "failed" in states.values()


# frob:tests python/sadi/server/routes_plugins.py::make_plugins_router
def test_get_one_and_404() -> None:
    get = _endpoint(_router(), "/api/plugins/{plugin_id}")
    assert get("lctt").id == "lctt"
    with pytest.raises(HTTPException) as ei:
        get("nope")
    assert ei.value.status_code == 404
