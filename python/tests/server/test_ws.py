"""Tests for the binary frame codec and the WebSocket stream."""

# frob:ticket 01M6W7R3ZPY606D3MHG4QRM2GS

from __future__ import annotations

import json
import struct
import threading
import time
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from sadi.core.pipeline import Bus, PipelineStopped, TraceFrame
from sadi.server import framing
from sadi.server.app import AppSettings, create_app
from sadi.server.ws import CLIENT_FRAME_DEPTH


def _frame(i: int, n: int = 256, t0: float | None = None) -> TraceFrame:
    return TraceFrame(
        raw_seq=i,
        t0_s=float(i) if t0 is None else t0,
        dt_s=2e-5,
        channels={0: [float(i)] * n, 1: list(np.linspace(-1, 1, n))},
        durable_seq=i,
        enqueued_seq=i + 1,
    )


def _client(bus: Bus) -> TestClient:
    return TestClient(create_app(AppSettings(data_root=Path("x"), bus=bus, require_root_lock=False)))


# frob:tests sadi.server.framing.encode_trace
def test_trace_roundtrip_and_layout() -> None:
    """Header is 24 bytes with magic; values survive as float32 min/max."""
    data = framing.encode_trace(7, 1.5, 2e-5, {0: [1.0, 2.0, 3.0], 2: [4.0, 5.0, 6.0]}, 9, 8, 10)
    assert data[:4] == b"SADI"
    assert struct.unpack_from("<BBH", data, 4) == (1, 1, 0)
    got = framing.decode(data).danger_ok
    assert got.seq == 7 and got.t0_s == 1.5 and got.trace is not None
    assert (got.trace.raw_seq, got.trace.durable_seq, got.trace.enqueued_seq) == (9, 8, 10)
    assert list(got.trace.mins[2]) == [4.0, 5.0, 6.0]


# frob:tests sadi.server.framing.minmax_decimate
def test_decimation_keeps_peaks() -> None:
    """A single spike survives min/max decimation."""
    v = np.zeros(10_000)
    v[4321] = 5.0
    mn, mx = framing.minmax_decimate(v, 100)
    assert mn.shape[0] == 100 and mx.max() == 5.0 and mn.min() == 0.0


# frob:tests sadi.server.framing.decode
def test_decode_rejects_bad_frames() -> None:
    """Short, wrong-magic, wrong-version and unknown-type frames are typed errors."""
    good = framing.encode_trace(1, 0.0, 1.0, {0: [1.0]}, 1, 1, 1)
    assert framing.decode(good[:10]).is_err
    assert framing.decode(b"XXXX" + good[4:]).is_err
    assert framing.decode(good[:4] + b"\x09" + good[5:]).is_err
    assert framing.decode(good[:5] + b"\x63" + good[6:]).is_err
    assert framing.decode(good[:-1]).is_err


# frob:tests sadi.server.framing.encode_envelope
def test_envelope_type_reserved_with_stale_flag() -> None:
    """The results-envelope frame type carries opaque JSON and the stale flag."""
    got = framing.decode(framing.encode_envelope(3, 0.0, b'{"v":1}', stale=True)).danger_ok
    assert got.type is framing.FrameType.RESULTS_ENVELOPE and got.stale and got.body == b'{"v":1}'


# frob:tests sadi.server.ws.make_ws_router
def test_hello_state_and_stop_pushed_as_json() -> None:
    """A client gets hello, then JSON for pipeline events, then a binary trace frame."""
    bus = Bus()
    with _client(bus).websocket_connect("/api/stream") as ws:
        assert json.loads(ws.receive_text())["kind"] == "hello"
        bus.publish(PipelineStopped(reason="r", hint="h", last_durable_seq=4))
        bus.publish(_frame(1))
        msg = json.loads(ws.receive_text())
        assert msg["kind"] == "stopped" and msg["last_durable_seq"] == 4
        fr = framing.decode(ws.receive_bytes()).danger_ok
        assert fr.trace is not None and fr.trace.raw_seq == 1


# frob:tests sadi.server.ws.StreamHub
def test_slow_client_drops_display_frames_with_counter() -> None:
    """Frames queued beyond the depth are dropped and counted, newest kept."""
    from sadi.server.ws import StreamHub

    bus = Bus()
    hub = StreamHub(bus)
    c = hub.attach()
    for i in range(CLIENT_FRAME_DEPTH + 5):
        bus.publish(_frame(i))
    hub.poll()
    assert c.stats.dropped_frames == 5
    assert len(c.frames) == CLIENT_FRAME_DEPTH
    assert c.frames[-1][1].raw_seq == CLIENT_FRAME_DEPTH + 4


# frob:tests sadi.server.ws.StreamHub.hello
def test_reconnect_resumes_from_latest() -> None:
    """A new connection gets the latest state in hello and no old frames."""
    bus = Bus()
    client = _client(bus)
    with client.websocket_connect("/api/stream") as ws:
        ws.receive_text()
        bus.publish(PipelineStopped(reason="r", hint="h", last_durable_seq=2))
        assert json.loads(ws.receive_text())["kind"] == "stopped"
    with client.websocket_connect("/api/stream") as ws:
        hello = json.loads(ws.receive_text())
        assert [m["kind"] for m in hello["latest"]] == ["stopped"]


# frob:tests sadi.server.ws.make_ws_router
def test_50ksps_real_time_budget() -> None:
    """50 kS/s as 1000-sample blocks every 20 ms for 2 s: >=95% delivered, p95 latency < 100 ms."""
    bus = Bus()
    n_frames = 100
    with _client(bus).websocket_connect("/api/stream") as ws:
        ws.receive_text()

        def produce() -> None:
            start = time.monotonic()
            for i in range(n_frames):
                bus.publish(_frame(i, t0=time.monotonic()))
                time.sleep(max(0.0, start + (i + 1) * 0.02 - time.monotonic()))

        t = threading.Thread(target=produce)
        t.start()
        lat: list[float] = []
        deadline = time.monotonic() + 5
        while len(lat) < n_frames and time.monotonic() < deadline:
            msg = ws.receive()
            if msg.get("bytes"):
                fr = framing.decode(msg["bytes"]).danger_ok
                lat.append(time.monotonic() - fr.t0_s)
            elif msg.get("text") and json.loads(msg["text"])["kind"] == "stats" and not t.is_alive():
                break
        t.join()
    assert len(lat) >= 0.95 * n_frames
    assert float(np.percentile(lat, 95)) < 0.1
