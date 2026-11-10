"""WebSocket stream: pipeline bus events pushed to the browser as binary and JSON messages.

`StreamHub` drains one bus `Subscription` and fans events out to per-client bounded queues.
Display frames are droppable (oldest first, counted); WAL data is never touched here because
the pipeline only publishes after a block is durable. State, results and guidance go as
JSON text messages. A reconnecting client gets a `hello` with the latest state and then
the live stream (no replay of missed frames). Session info comes from `SessionService`.
"""

# frob:ticket 01M6W7R3ZPY606D3MHG4QRM2GS
# frob:ticket 01M6WWN90MKGKGY4H7Y8PWYEQZ
# frob:ticket 01M6X9NXWB7KW3ZGQP02KDWN8N
# frob:ticket 01M6XA16Y0GEC333HA645FY2YX

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, ConfigDict

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
from sadi.jobs.state import ResultEnvelope, ResultState
from sadi.labs.lctt.guidance import GuidanceState, Phase
from sadi.logging_setup import get_logger
from sadi.server.framing import encode_envelope, encode_trace
from sadi.server.results_stream import Connection, ResultsStream
from sadi.server.service import SessionService
from sadi.synthetic.provenance import REAL, DataProvenance

_log = get_logger(__name__)

#: Display frames a client may have queued before the oldest is dropped.
CLIENT_FRAME_DEPTH = 8
#: JSON messages a client may have queued (state/results are not dropped before this).
CLIENT_JSON_DEPTH = 1024
POLL_S = 0.01
#: Highest rate at which `state` messages are sent (latest wins); raw data is unaffected.
STATE_MAX_HZ = 30.0  # frob:ticket 01M7230X8BYK2RJAG749SST7TB
STATS_PERIOD_S = 1.0


def _json_of(event: BusEvent) -> dict[str, Any] | None:
    """Map a non-trace bus event to its JSON side-channel message.

    `state` also carries `drift_vps` (server drift rate, V/s, or null); the hub adds the
    capture window and `simulated`.
    """
    if isinstance(event, SettleUpdate):
        drift = event.status.drift_rate
        return {
            "kind": "state",
            "raw_seq": event.raw_seq,
            "drift_vps": drift.value if drift is not None else None,
            "status": event.status.model_dump(mode="json"),
        }
    if isinstance(event, ResultUpdate):
        return {
            "kind": "result",
            "raw_seq": event.raw_seq,
            "record": event.record.model_dump(mode="json"),
        }
    if isinstance(event, AnalysisFailed):
        return {"kind": "analysis_failed", "raw_seq": event.raw_seq, "reason": event.reason}
    if isinstance(event, PipelineStopped):
        return {"kind": "stopped", **event.model_dump(mode="json")}
    return None


class GuidancePayload(BaseModel):
    """Payload of the WS `guidance` message: the guided-run next step and stop advice."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    phase: Phase
    next_action: str
    stop_early: bool = False
    stop_reason: str = ""

    @classmethod
    def from_state(cls, state: GuidanceState) -> GuidancePayload:
        """Project a full GuidanceState onto the WS payload."""
        return cls(
            phase=state.phase,
            next_action=state.next_action,
            stop_early=state.stop_early,
            stop_reason=state.stop_reason,
        )


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
        self.envelopes: deque[ResultEnvelope] = deque()
        self.conn: Connection | None = None
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

    def offer_envelope(self, env: ResultEnvelope) -> None:
        """Queue a versioned result envelope; the oldest goes first at the generous cap."""
        if len(self.envelopes) >= CLIENT_JSON_DEPTH:
            self.envelopes.popleft()
            _log.warning("client envelope queue full; oldest envelope dropped")
        self.envelopes.append(env)


def encode_result(seq: int, env: ResultEnvelope) -> bytes:
    """Encode `env` as a RESULTS_ENVELOPE frame (JSON body, stale flag from its state)."""
    return encode_envelope(
        seq,
        env.emitted_ns / 1e9,
        env.model_dump_json().encode("utf-8"),
        stale=env.state is ResultState.STALE,
    )


class StreamHub:
    """Fans the pipeline bus out to WebSocket clients and remembers the latest state."""

    def __init__(
        self,
        bus: Bus,
        sessions: SessionService | None = None,
        results: ResultsStream | None = None,
        simulated: Callable[[], bool] | None = None,
        guidance: Callable[[], GuidancePayload | None] | None = None,
        provenance: DataProvenance = REAL,
    ) -> None:
        """Subscribe once to `bus`; `sessions` supplies `hello` info, `results` the envelopes.

        `simulated` reports whether the data source is the simulator (stamped on `hello` and
        `state` messages; absent means false). `guidance` computes the current payload; it is
        consulted after each result or settle-state change and published when it changed.
        """
        self._guidance = guidance
        self._provenance = provenance  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
        self._last_guidance: GuidancePayload | None = None
        self._last_settle: str | None = None
        self.results = results
        self._simulated = simulated
        self._window_point: int | None = None
        self._window_first = 0
        self._sub: Subscription = bus.subscribe("ws-hub")
        self._sessions = sessions
        self._lock = threading.Lock()
        # frob:ticket 01M72854VNXD656XAJNYNKX6Y1
        self._poll_lock = threading.Lock()
        self._clients: list[_Client] = []
        self._seq = 0
        self._latest: dict[str, dict[str, Any]] = {}
        self._pending_state: dict[str, Any] | None = None  # frob:ticket 01M7230X8BYK2RJAG749SST7TB
        self._last_state_sent = 0.0

    def next_seq(self) -> int:
        """Allocate the next hub-wide frame sequence number."""
        with self._lock:
            self._seq += 1
            return self._seq

    def attach(self) -> _Client:
        """Register a client; it sees only events from now on (resume from latest)."""
        c = _Client()
        if self.results is not None:
            c.conn = self.results.connect(c.offer_envelope)
        with self._lock:
            self._clients.append(c)
        _log.info("ws client attached (%d total)", len(self._clients))
        return c

    def detach(self, client: _Client) -> None:
        """Remove a client."""
        if self.results is not None and client.conn is not None:
            self.results.disconnect(client.conn)
        with self._lock:
            if client in self._clients:
                self._clients.remove(client)
        _log.info("ws client detached; dropped_frames=%d", client.stats.dropped_frames)

    def publish_guidance(self, payload: GuidancePayload) -> None:
        """Push a typed guidance message (JSON side channel) to every client."""
        _log.info("publishing guidance phase=%s stop_early=%s", payload.phase, payload.stop_early)
        self._last_guidance = payload
        self._fanout_msg({"kind": "guidance", **payload.model_dump(mode="json")})

    def is_simulated(self) -> bool:
        """True when the data source is the simulator."""
        return self._simulated is not None and self._simulated()

    def _stamp_state(self, msg: dict[str, Any]) -> None:
        """Add the capture window (first/last raw seq of the open point) and `simulated`."""
        point = msg["status"].get("point_index")
        if point != self._window_point:
            self._window_point = point
            self._window_first = msg["raw_seq"]
            _log.info("capture window opened: point=%s first_raw_seq=%d", point, self._window_first)
        msg["window"] = {"first_raw_seq": self._window_first, "last_raw_seq": msg["raw_seq"]}
        msg["simulated"] = self.is_simulated()
        msg["provenance"] = self._provenance.model_dump(
            mode="json"
        )  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC

    def poll(self) -> None:
        """Drain the bus subscription and distribute events to clients (thread-safe, in order)."""
        # frob:ticket 01M72854VNXD656XAJNYNKX6Y1
        with self._poll_lock:
            self._poll_locked()

    def _poll_locked(self) -> None:
        """Body of `poll`; the caller holds `_poll_lock` so drain order equals delivery order."""
        events = self._sub.drain()
        if not events:
            self._flush_state()
            return
        changed = False
        with self._lock:
            for ev in events:
                if isinstance(ev, ResultUpdate):
                    changed = True
                elif isinstance(ev, SettleUpdate) and ev.status.state.value != self._last_settle:
                    self._last_settle = ev.status.state.value
                    changed = True
                if isinstance(ev, TraceFrame):
                    self._seq += 1
                    for c in self._clients:
                        c.offer_frame(self._seq, ev)
                    continue
                msg = _json_of(ev)
                if msg is None:
                    _log.error("unmapped bus event %s", type(ev).__name__)
                    continue
                if msg["kind"] == "state":
                    self._stamp_state(msg)
                if msg["kind"] == "state":
                    self._pending_state = msg  # coalesce: the latest state wins
                    continue
                self._latest[msg["kind"]] = msg
                for c in self._clients:
                    c.offer_msg(msg)
        self._flush_state()
        if changed:
            self.refresh_guidance()

    def _flush_state(self) -> None:
        """Send the pending (latest) `state` message if the STATE_MAX_HZ interval has passed."""
        # frob:ticket 01M7230X8BYK2RJAG749SST7TB
        with self._lock:
            msg = self._pending_state
            now = time.monotonic()
            if msg is None or now - self._last_state_sent < 1.0 / STATE_MAX_HZ:
                return
            self._pending_state = None
            self._last_state_sent = now
            self._latest["state"] = msg
            for c in self._clients:
                c.offer_msg(msg)

    def refresh_guidance(self) -> bool:
        """Recompute guidance and publish it unless identical to the last one; True if sent."""
        if self._guidance is None:
            return False
        payload = self._guidance()
        if payload is None or payload == self._last_guidance:
            return False
        self.publish_guidance(payload)
        return True

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
        return {
            "kind": "hello",
            "session": session,
            "latest": latest,
            "simulated": self.is_simulated(),
            "provenance": self._provenance.model_dump(mode="json"),
            "bus_dropped": self._sub.dropped,
        }


def make_ws_router(hub: StreamHub) -> APIRouter:
    """Build the router exposing `/api/stream`."""
    router = APIRouter()

    @router.websocket("/api/stream")
    async def stream(ws: WebSocket) -> None:
        """Push binary trace frames and JSON messages until the client leaves."""
        await ws.accept()
        # frob:ticket 01M72854VNXD656XAJNYNKX6Y1
        client = await asyncio.to_thread(hub.attach)
        last_stats = time.monotonic()
        try:
            await ws.send_text(json.dumps(await asyncio.to_thread(hub.hello)))
            while True:
                await asyncio.to_thread(hub.poll)
                busy = False
                while client.msgs:
                    await ws.send_text(json.dumps(client.msgs.popleft()))
                    busy = True
                while client.envelopes:
                    await ws.send_bytes(encode_result(await asyncio.to_thread(hub.next_seq), client.envelopes.popleft()))
                    busy = True
                while client.frames:
                    seq, f = client.frames.popleft()
                    await ws.send_bytes(
                        encode_trace(
                            seq,
                            f.t0_s,
                            f.dt_s,
                            f.channels,
                            f.raw_seq,
                            f.durable_seq,
                            f.enqueued_seq,
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
            # shielded so a cancelled handler still detaches (no leaked client)
            await asyncio.shield(asyncio.to_thread(hub.detach, client))

    return router
