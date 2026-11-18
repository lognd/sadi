"""The WS handler must not block the event loop on hub-locked work."""

# frob:ticket 01M72854VNXD656XAJNYNKX6Y1
# creates:python/tests/server/test_ws_offloop.py

from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

from fastapi import WebSocketDisconnect

from sadi.core.pipeline import Bus
from sadi.server.ws import StreamHub, make_ws_router


class _FakeWS:
    """Minimal WebSocket stand-in recording sent text and disconnecting on demand."""

    def __init__(self) -> None:
        self.texts: list[str] = []
        self.stop = asyncio.Event()

    async def accept(self) -> None:
        """Accept the connection (no-op)."""

    async def send_text(self, data: str) -> None:
        """Record a text frame; disconnect once asked to stop."""
        if self.stop.is_set():
            raise WebSocketDisconnect()
        self.texts.append(data)

    async def send_bytes(self, data: bytes) -> None:
        """Binary frames are not needed here."""


# frob:tests python/sadi/server/ws.py::make_ws_router
# frob:tests python/sadi/server/ws.py::StreamHub.next_seq
# frob:tests python/sadi/server/ws.py::StreamHub.poll
def test_loop_stays_responsive_while_hub_lock_held() -> None:
    """A held hub lock must stall only the handler thread, never the event loop."""
    hub = StreamHub(Bus())
    handler: Any = next(r for r in make_ws_router(hub).routes if r.path == "/api/stream").endpoint  # type: ignore[attr-defined]
    hold_s = 0.6
    release = threading.Event()

    def holder() -> None:
        with hub._lock:  # noqa: SLF001
            release.wait(hold_s)

    async def scenario() -> float:
        ws = _FakeWS()
        t = threading.Thread(target=holder)
        t.start()
        time.sleep(0.05)  # holder owns the lock before the handler starts
        task = asyncio.create_task(handler(ws))
        worst = 0.0
        end = time.monotonic() + hold_s
        last = time.monotonic()
        while time.monotonic() < end:
            await asyncio.sleep(0.01)
            now = time.monotonic()
            worst = max(worst, now - last)
            last = now
        release.set()
        t.join()
        await asyncio.sleep(0.2)
        assert ws.texts, "hello must be delivered once the lock frees (no frame lost)"
        ws.stop.set()
        await asyncio.wait_for(task, 5)
        return worst

    worst = asyncio.run(scenario())
    assert worst < 0.25, f"event loop stalled {worst:.3f}s while the hub lock was held"
