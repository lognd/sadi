"""WebSocket stream: pipeline bus events pushed to the browser as binary and JSON messages.

`StreamHub` drains one bus `Subscription` and fans events out to per-client bounded queues.
Display frames are droppable (oldest first, counted); WAL data is never touched here because
the pipeline only publishes after a block is durable. State, results and guidance go as
JSON text messages. A reconnecting client gets a `hello` with the latest state and then
the live stream (no replay of missed frames). Session info comes from `SessionService`.
"""

# frob:ticket 01M6W7R3ZPY606D3MHG4QRM2GS

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from sadi.core.pipeline import (
    AnalysisFailed,
    Bus,
    BusEvent,
    PipelineStopped,
    ResultUpdate,
    SettleUpdate,
    Subscription,
    TraceFrame,
)
from sadi.logging_setup import get_logger
from sadi.server.framing import encode_trace
from sadi.server.service import SessionService

_log = get_logger(__name__)

#: Display frames a client may have queued before the oldest is dropped.
CLIENT_FRAME_DEPTH = 8
#: JSON messages a client may have queued (state/results are not dropped before this).
CLIENT_JSON_DEPTH = 1024
POLL_S = 0.01
STATS_PERIOD_S = 1.0


def _json_of(event: BusEvent) -> dict[str, Any] | None:
    """Map a non-trace bus event to its JSON side-channel message."""
    if isinstance(event, SettleUpdate):
        return {"kind": "state", "raw_seq": event.raw_seq, "status": event.status.model_dump(mode="json")}
    if isinstance(event, ResultUpdate):
        return {"kind": "result", "raw_seq": event.raw_seq, "record": event.record.model_dump(mode="json")}
    if isinstance(event, AnalysisFailed):
        return {"kind": "analysis_failed", "raw_seq": event.raw_seq, "reason": event.reason}
    if isinstance(event, PipelineStopped):
        return {"kind": "stopped", **event.model_dump(mode="json")}
    return None


class ClientStats(BaseModel):
    """Per-client counters sent in `stats` messages."""

    sent_frames: int = 0
    dropped_frames: int = 0


class _Client:
    """One connection's bounded queues and counters."""

    def __init__(self) -> None:
        """Start empty."""
        self.frames: deque[tuple[int, TraceFrame]] = deque()
        self.msgs: deque[dict[str, Any]] = deque()
        self.stats = ClientStats()

    def offer_frame(self, seq: int, frame: TraceFrame) -> None:
        """Queue a display frame, dropping (and counting) the oldest when full."""
        if len(self.frames) >= CLIENT_FRAME_DEPTH:
            self.frames.popleft()
            self.stats.dropped_frames += 1
        self.frames.append((seq, frame))

    def offer_msg(self, msg: dict[str, Any]) -> None:
        """Queue a JSON message, evicting the oldest only at the generous cap."""
        if len(self.msgs) >= CLIENT_JSON_DEPTH:
            self.msgs.popleft()
            _log.warning("client json queue full; oldest message dropped")
        self.msgs.append(msg)


class StreamHub:
    """Fans the pipeline bus out to WebSocket clients and remembers the latest state."""

    def __init__(self, bus: Bus, sessions: SessionService | None = None) -> None:
        """Subscribe once to `bus`; `sessions` (optional) supplies session info for `hello`."""
        self._sub: Subscription = bus.subscribe("ws-hub")
        self._sessions = sessions
        self._lock = threading.Lock()
        self._clients: list[_Client] = []
        self._seq = 0
        self._latest: dict[str, dict[str, Any]] = {}

    def attach(self) -> _Client:
        """Register a client; it sees only events from now on (resume from latest)."""
        c = _Client()
        with self._lock:
            self._clients.append(c)
        _log.info("ws client attached (%d total)", len(self._clients))
        return c

    def detach(self, client: _Client) -> None:
        """Remove a client."""
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)
        _log.info("ws client detached; dropped_frames=%d", client.stats.dropped_frames)

    def publish_guidance(self, message: dict[str, Any]) -> None:
        """Push a guidance message (JSON side channel) to every client."""
        self._fanout_msg({"kind": "guidance", **message})

    def poll(self) -> None:
        """Drain the bus subscription and distribute events to clients."""
        events = self._sub.drain()
        if not events:
            return
        with self._lock:
            for ev in events:
                if isinstance(ev, TraceFrame):
                    self._seq += 1
                    for c in self._clients:
                        c.offer_frame(self._seq, ev)
                    continue
                msg = _json_of(ev)
                if msg is None:
                    _log.error("unmapped bus event %s", type(ev).__name__)
                    continue
                self._latest[msg["kind"]] = msg
                for c in self._clients:
                    c.offer_msg(msg)

    def _fanout_msg(self, msg: dict[str, Any]) -> None:
        """Queue `msg` for every client."""
        with self._lock:
            self._latest[msg["kind"]] = msg
            for c in self._clients:
                c.offer_msg(msg)

    def hello(self) -> dict[str, Any]:
        """Build the first message of a connection: session info and the latest messages."""
        session: Any = None
        if self._sessions is not None:
            info = self._sessions.info()
            session = info.danger_ok.model_dump(mode="json") if info.is_ok else None
        with self._lock:
            latest = list(self._latest.values())
        return {"kind": "hello", "session": session, "latest": latest, "bus_dropped": self._sub.dropped}


def make_ws_router(hub: StreamHub) -> APIRouter:
    """Build the router exposing `/api/stream`."""
    router = APIRouter()

    @router.websocket("/api/stream")
    async def stream(ws: WebSocket) -> None:
        """Push binary trace frames and JSON messages until the client leaves."""
        await ws.accept()
        client = hub.attach()
        last_stats = time.monotonic()
        try:
            await ws.send_text(json.dumps(hub.hello()))
            while True:
                hub.poll()
                busy = False
                while client.msgs:
                    await ws.send_text(json.dumps(client.msgs.popleft()))
                    busy = True
                while client.frames:
                    seq, f = client.frames.popleft()
                    await ws.send_bytes(
                        encode_trace(
                            seq, f.t0_s, f.dt_s, f.channels, f.raw_seq, f.durable_seq, f.enqueued_seq
                        )
                    )
                    client.stats.sent_frames += 1
                    busy = True
                now = time.monotonic()
                if now - last_stats >= STATS_PERIOD_S:
                    last_stats = now
                    await ws.send_text(json.dumps({"kind": "stats", **client.stats.model_dump()}))
                if not busy:
                    await asyncio.sleep(POLL_S)
        except (WebSocketDisconnect, RuntimeError) as exc:
            _log.info("ws client left: %s", type(exc).__name__)
        finally:
            hub.detach(client)

    return router
