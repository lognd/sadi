"""Origin/Host guard: blocks DNS rebinding and cross-site writes against the local server."""

# frob:ticket 01M729645YNC58VB5NTJE6Q1RK

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any
from urllib.parse import urlsplit

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

Scope = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[MutableMapping[str, Any]]]
Send = Callable[[MutableMapping[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

#: Host names that denote this machine ("testserver" is Starlette's TestClient, never routable).
LOCAL_HOSTS: frozenset[str] = frozenset({"localhost", "127.0.0.1", "::1", "testserver"})
_SAFE_METHODS: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})
_DEFAULT_PORTS = {"http": 80, "ws": 80, "https": 443, "wss": 443}


def split_hostport(netloc: str) -> tuple[str, int | None]:
    """Split a Host `netloc` into (lowercase hostname, port or None); bad input is ("", None)."""
    try:
        parts = urlsplit(f"//{netloc}")
        return (parts.hostname or "").lower(), parts.port
    except ValueError:
        return "", None


def host_allowed(host_header: str) -> bool:
    """Return whether a Host header names this machine (localhost, 127.0.0.1, [::1])."""
    return split_hostport(host_header)[0] in LOCAL_HOSTS


def origin_allowed(origin: str, host_header: str, extra: frozenset[str] = frozenset()) -> bool:
    """Return whether `origin` is local and on the port the request was served on."""
    if origin in extra:
        return True
    parts = urlsplit(origin)
    try:
        port = parts.port
    except ValueError:
        return False
    if (parts.hostname or "").lower() not in LOCAL_HOSTS:
        return False
    served = split_hostport(host_header)[1]
    default = _DEFAULT_PORTS.get(parts.scheme)
    return (port if port is not None else default) == (served if served is not None else default)


class OriginGuard:
    """ASGI middleware: 403 on non-local Host, foreign Origin or cross-site writes/WS."""

    def __init__(self, app: ASGIApp, extra_origins: frozenset[str] = frozenset()) -> None:
        """Wrap `app`; `extra_origins` are additional exact Origins to trust (e.g. a dev server)."""
        self._app = app
        self._extra = extra_origins

    def _verdict(self, scope: Scope) -> str | None:
        """Return the refusal reason for this request, or None when it may proceed."""
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope["headers"]}
        host = headers.get("host", "")
        if not host_allowed(host):
            return f"non-local Host {host!r}"
        # frob:ticket 01M72D3CTDED2MGDY721RSM8M4
        # GET /api/export/* writes a saved copy, so a cross-site page must not trigger it.
        path = str(scope.get("path", ""))
        if headers.get("sec-fetch-site") == "cross-site" and path.startswith("/api/"):
            return "Sec-Fetch-Site cross-site"
        guarded = scope["type"] == "websocket" or scope.get("method", "GET") not in _SAFE_METHODS
        if not guarded:
            return None
        if headers.get("sec-fetch-site") == "cross-site":
            return "Sec-Fetch-Site cross-site"
        origin = headers.get("origin")
        if origin is not None and not origin_allowed(origin, host, self._extra):
            return f"foreign Origin {origin!r}"
        return None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Pass lifespan through; refuse http/websocket requests that fail the guard."""
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return
        why = self._verdict(scope)
        if why is None:
            await self._app(scope, receive, send)
            return
        _log.warning("refused %s %s: %s", scope["type"], scope.get("path"), why)
        if scope["type"] == "websocket":
            await receive()
            await send({"type": "websocket.close", "code": 1008})
            return
        body = json.dumps(
            {
                "type": "about:blank",
                "title": "Forbidden",
                "status": 403,
                "detail": why,
                "hint": "Open SADI from http://localhost on the served port.",
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/problem+json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
