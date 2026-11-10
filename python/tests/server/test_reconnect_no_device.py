"""No board at start: disconnected status, sessions open, capture blocked, Reconnect attaches."""

# frob:ticket 01M724AKWJV8BRNRR3Q43553VR
from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.device import DeviceService, DeviceSource, DeviceStatus
from sadi.core.pipeline import Bus
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.server.live import STOP_NO_DEVICE, LiveAcquisition, LiveError
from sadi.store.records import RecordType
from sadi.store.wal import WalReader

_CAPTURE = {
    "phase": "calibrate",
    "inputs": {},
    "window": {"first_raw_seq": 1, "last_raw_seq": 1},
}


def _types(root: Path) -> list[int]:
    """Record types of the only session's WAL, in order."""
    wal_dir = next((root / "sessions").iterdir()) / "wal"
    return [int(r.danger_ok.type) for r in WalReader(wal_dir).records() if r.is_ok]


@contextmanager
def _app(tmp_path: Path) -> Generator[tuple[TestClient, DeviceService, LiveAcquisition]]:
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    dev = DeviceService(DeviceSource(kind="sim", manual_load=True))  # never opened
    live = LiveAcquisition(dev, Bus(), watch_poll_s=3600.0)
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
    with TestClient(app) as c:
        try:
            yield c, dev, live
        finally:
            c.post("/api/session/close")
    dev.close()


# frob:tests python/sadi/core/device.py::DeviceService.status
# frob:tests python/sadi/core/device.py::DeviceStatus
# frob:tests python/sadi/server/routes/results.py::device_status
def test_status_is_disconnected_before_attach(tmp_path: Path) -> None:
    """An unopened service reports disconnected, unattached, with a plug-in hint."""
    with _app(tmp_path) as (c, dev, _live):
        assert dev.status == DeviceStatus.DISCONNECTED
        view = c.get("/api/device/status").json()
        assert view["status"] == "disconnected" and view["attached"] is False
        assert "Reconnect" in view["hint"]


# frob:tests python/sadi/server/live.py::LiveAcquisition.on_session_open
# frob:tests python/sadi/server/live.py::LiveAcquisition.capture_block_hint
# frob:tests python/sadi/server/service.py::SessionService.capture
def test_session_opens_without_device_and_capture_is_blocked(tmp_path: Path) -> None:
    """No RuntimeError opening a session; capture and load change are refused with a hint."""
    with _app(tmp_path) as (c, _dev, live):
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "s"}).status_code == 201
        assert live.stop_reason == STOP_NO_DEVICE and not live.running
        assert live.fault is not None
        got = c.post("/api/session/points", json=_CAPTURE)
        assert got.status_code == 409
        assert "Reconnect" in got.json()["hint"]
        assert live.mark_load_change().danger_err == LiveError.NoDevice
        assert RecordType.RAW_BLOCK not in _types(tmp_path)


# frob:tests python/sadi/server/live.py::LiveAcquisition.reconnect_device
# frob:tests python/sadi/server/routes/results.py::reconnect_device
def test_reconnect_attaches_mid_session_without_touching_the_wal(tmp_path: Path) -> None:
    """Reconnect starts recording into the open session; prior records stay as they were."""
    with _app(tmp_path) as (c, dev, live):
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "s"}).status_code == 201
        before = _types(tmp_path)
        view = c.post("/api/device/reconnect").json()
        assert view["status"] == "simulated" and view["attached"] is True
        assert dev.status == DeviceStatus.SIMULATED and live.running
        assert live.capture_block_hint() is None
        time.sleep(0.5)
        after = _types(tmp_path)
        assert after[: len(before)] == before  # existing records untouched, only appended to
        assert RecordType.SETTINGS in after[len(before) :]
        assert after.index(RecordType.SETTINGS) < after.index(RecordType.RAW_BLOCK)
        assert c.post("/api/device/reconnect").status_code == 200  # idempotent while running


# frob:tests python/sadi/server/routes/results.py::reconnect_device
def test_reconnect_failure_is_a_409_with_hint(tmp_path: Path) -> None:
    """A board that is still absent gives a 409 problem; status is error or disconnected."""
    labs = LabRegistry()
    dev = DeviceService(DeviceSource(kind="serial", port="/dev/does-not-exist"))
    live = LiveAcquisition(dev, Bus(), watch_poll_s=3600.0)
    app = create_app(
        AppSettings(data_root=tmp_path, labs=labs, device=dev, bus=live.bus, live=live,
                    require_root_lock=False)
    )
    with TestClient(app) as c:
        got = c.post("/api/device/reconnect")
        assert got.status_code == 409 and got.json()["hint"]
        assert c.get("/api/device/status").json()["status"] in ("error", "disconnected")
