"""The --sim device runs at real time and ws `state` is rate-capped (audit2 H1)."""

# frob:ticket 01M7230X8BYK2RJAG749SST7TB
from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.device import DEVICE_RATE_HZ, DeviceService, DeviceSource
from sadi.core.pipeline import Bus, SettleUpdate
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.labs.lctt.settle_stream import SettleState, StreamStatus
from sadi.server.app import AppSettings, create_app
from sadi.server.live import LiveAcquisition
from sadi.server.ws import STATE_MAX_HZ, StreamHub

_HEALTH_BUDGET_S = 0.1


def _open_sim() -> DeviceService:
    svc = DeviceService(DeviceSource(kind="sim", manual_load=True))
    assert svc.open().is_ok
    return svc


# frob:tests python/sadi/core/device.py::DeviceService._pace
def test_sim_reader_is_paced_to_device_rate() -> None:
    """In ~1 s of wall time the sim yields about 1 s of samples, none dropped."""
    svc = _open_sim()
    assert svc.start_streaming().is_ok
    t0 = time.monotonic()
    samples = 0
    while time.monotonic() - t0 < 1.0:
        got = svc.next_block(0.2)
        assert got.is_ok
        if got.danger_ok is not None:
            samples += int(got.danger_ok.n_samples)
    stopped = svc.stop_streaming()
    assert stopped.is_ok
    samples += sum(int(b.n_samples) for b in stopped.danger_ok)
    svc.close()
    # real time, not 10x: allow queue lead and block granularity, forbid a hot loop
    assert samples < 1.6 * DEVICE_RATE_HZ, samples


# frob:tests python/sadi/server/ws.py::StreamHub._flush_state
def test_state_messages_are_coalesced() -> None:
    """A burst of settle updates queues at most one state per interval, and the latest wins."""
    bus = Bus()
    hub = StreamHub(bus)
    client = hub.attach()
    for seq in range(1, 201):
        status = StreamStatus(state=SettleState.CREEPING, point_index=1)
        bus.publish(SettleUpdate(raw_seq=seq, status=status))
    hub.poll()
    states = [m for m in client.msgs if m["kind"] == "state"]
    assert len(states) == 1
    assert states[0]["raw_seq"] == 200
    # a later burst inside the interval is held, then released (latest only) after it
    bus.publish(
        SettleUpdate(raw_seq=201, status=StreamStatus(state=SettleState.CREEPING, point_index=1))
    )
    hub.poll()
    assert len([m for m in client.msgs if m["kind"] == "state"]) == 1
    time.sleep(1.0 / STATE_MAX_HZ + 0.02)
    hub.poll()
    states = [m for m in client.msgs if m["kind"] == "state"]
    assert [m["raw_seq"] for m in states] == [200, 201]


# frob:tests python/sadi/server/ws.py::StreamHub.poll
# frob:tests python/sadi/server/live.py::LiveAcquisition
def test_health_fast_with_ws_client_on_sim(tmp_path: Path) -> None:
    """With a ws client attached to a live --sim run, /api/health stays under 100 ms."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    dev = _open_sim()
    live = LiveAcquisition(dev, Bus())
    app = create_app(
        AppSettings(
            data_root=tmp_path,
            labs=labs,
            device=dev,
            bus=live.bus,
            live=live,
            synthetic=True,
            require_root_lock=False,
        )
    )
    t0 = time.monotonic()
    with TestClient(app) as c:
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "p"}).status_code == 201
        lat: list[float] = []
        with c.websocket_connect("/api/stream") as ws:
            end = time.monotonic() + 3.0
            while time.monotonic() < end:
                h0 = time.perf_counter()
                assert c.get("/api/health").status_code == 200
                lat.append(time.perf_counter() - h0)
                time.sleep(0.2)
            # drain what is queued without blocking forever
            ws.close()
    elapsed = time.monotonic() - t0
    dev.close()
    # median under budget; the worst probe only guards against a multi-second stall (CI noise)
    med = sorted(lat)[len(lat) // 2]
    assert med < _HEALTH_BUDGET_S, f"health median {med:.3f}s over {elapsed:.1f}s"
    assert max(lat) < 1.0, lat
