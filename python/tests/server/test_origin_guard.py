"""Origin/Host guard: foreign pages and rebinding hosts cannot drive the local API."""

# frob:ticket 01M729645YNC58VB5NTJE6Q1RK

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from sadi.plugins import PluginRegistry
from sadi.plugins.builtin import builtin_source
from sadi.server.app import AppSettings, create_app
from sadi.server.security import host_allowed, origin_allowed

_WRITES = [
    "/api/session/undo",
    "/api/session/redo",
    "/api/session/close",
    "/api/session/export",
    "/api/session/resume",
    "/api/device/reconnect",
]


def _client(**kw: object) -> TestClient:
    reg = PluginRegistry.discover([builtin_source()])
    return TestClient(create_app(AppSettings(registry=reg, data_root=Path("x"), **kw)))  # type: ignore[arg-type]


@pytest.mark.parametrize("path", _WRITES)
# frob:tests python/sadi/server/security.py::OriginGuard.__call__
def test_foreign_origin_post_refused(path: str) -> None:
    """A POST carrying a foreign Origin is a 403 before any handler runs."""
    res = _client().post(path, headers={"Origin": "http://evil.example"})
    assert res.status_code == 403


@pytest.mark.parametrize("path", _WRITES)
def test_cross_site_fetch_metadata_refused(path: str) -> None:
    """Sec-Fetch-Site: cross-site is refused even with no Origin header."""
    res = _client().post(path, headers={"Sec-Fetch-Site": "cross-site"})
    assert res.status_code == 403


# frob:tests python/sadi/server/security.py::OriginGuard._verdict
def test_non_local_host_refused_even_for_get() -> None:
    """DNS rebinding: a non-local Host is refused for reads too."""
    res = _client().get("/api/plugins", headers={"Host": "evil.example"})
    assert res.status_code == 403


def test_local_get_and_no_origin_post_allowed() -> None:
    """Plain GET and an Origin-less POST (curl, tests) reach the handler."""
    c = _client()
    assert c.get("/api/plugins").status_code == 200
    assert c.post("/api/session/undo").status_code != 403


@pytest.mark.parametrize(
    "origin", ["http://localhost:8765", "http://127.0.0.1:8765", "http://[::1]:8765"]
)
def test_local_origin_on_served_port_allowed(origin: str) -> None:
    """Same-origin local pages on the served port pass the guard."""
    res = _client().post(
        "/api/session/undo", headers={"Origin": origin, "Host": origin.split("//")[1]}
    )
    assert res.status_code != 403


def test_local_origin_wrong_port_refused() -> None:
    """A different local port is another web app, so it is refused."""
    res = _client().post(
        "/api/session/undo",
        headers={"Origin": "http://localhost:9999", "Host": "localhost:8765"},
    )
    assert res.status_code == 403


def test_extra_origin_trusted() -> None:
    """A configured dev-server Origin is accepted."""
    c = _client(extra_origins=frozenset({"http://localhost:5173"}))
    res = c.post(
        "/api/session/undo",
        headers={"Origin": "http://localhost:5173", "Host": "localhost:8765"},
    )
    assert res.status_code != 403


# frob:tests python/sadi/server/security.py::OriginGuard.__init__
def test_websocket_foreign_origin_refused() -> None:
    """The WebSocket handshake with a foreign Origin is closed before accept."""
    c = _client()
    with (
        pytest.raises(WebSocketDisconnect),
        c.websocket_connect("/api/stream", headers={"Origin": "http://evil.example"}),
    ):
        pass


# frob:tests python/sadi/server/security.py::host_allowed
# frob:tests python/sadi/server/security.py::origin_allowed
# frob:tests python/sadi/server/security.py::split_hostport
def test_helpers() -> None:
    """host_allowed / origin_allowed unit behaviour."""
    assert host_allowed("localhost:8765") and host_allowed("[::1]:1")
    assert not host_allowed("evil.example") and not host_allowed("")
    assert not origin_allowed("http://localhost.evil.example:8765", "localhost:8765")
