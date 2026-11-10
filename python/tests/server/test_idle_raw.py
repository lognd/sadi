"""Raw streaming stops when the session is finished/idle or disk is low; data is never dropped."""

# frob:ticket 01M723P32SR45XWMW7BE5QZE7H
from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.device import DeviceService, DeviceSource, free_bytes
from sadi.core.pipeline import Bus
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.server.live import STOP_FINISHED, STOP_IDLE, STOP_LOW_DISK, LiveAcquisition
from sadi.store.records import RecordType
from sadi.store.wal import WalReader


class _Clock:
    """Manually advanced monotonic clock."""

    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


def _raw_count(root: Path) -> int:
    wal_dir = next((root / "sessions").iterdir()) / "wal"
    return sum(
        1
        for r in WalReader(wal_dir).records()
        if r.is_ok and RecordType(r.danger_ok.type) == RecordType.RAW_BLOCK
    )


@contextmanager
def _session(
    tmp_path: Path, clock: _Clock, **kw: float
) -> Iterator[tuple[TestClient, LiveAcquisition]]:
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    dev = DeviceService(DeviceSource(kind="sim", manual_load=True))
    assert dev.open().is_ok
    live = LiveAcquisition(dev, Bus(), watch_poll_s=3600.0, clock=clock, **kw)  # type: ignore[arg-type]
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
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "s"}).status_code == 201
        try:
            yield c, live
        finally:
            c.post("/api/session/close")
    dev.close()


# frob:tests python/sadi/server/live.py::LiveAcquisition.check_once
def test_idle_timeout_stops_raw_without_losing_blocks(tmp_path: Path) -> None:
    """After the idle timeout no more RAW_BLOCKs are written; earlier ones stay."""
    clock = _Clock()
    with _session(tmp_path, clock, idle_timeout_s=10.0) as (c, live):
        time.sleep(0.5)
        clock.t = 11.0
        live.check_once()
        assert live.stop_reason == STOP_IDLE
        assert not live.running
        n = _raw_count(tmp_path)
        assert n > 0
        time.sleep(0.5)
        assert _raw_count(tmp_path) == n
        # A new load change resumes streaming after idle.
        assert live.mark_load_change().is_ok
        assert live.running
        c.post("/api/session/close")


# frob:tests python/sadi/server/live.py::LiveAcquisition.finish
# frob:tests python/sadi/server/live.py::LiveAcquisition.stop_reason
# frob:tests python/sadi/server/live.py::LiveAcquisition.stop_streaming
def test_finish_stops_raw_and_refuses_restart(tmp_path: Path) -> None:
    """finish() drains and stops; a later load change is refused, not silently restarted."""
    with _session(tmp_path, _Clock()) as (_c, live):
        time.sleep(0.4)
        assert live.finish().is_ok
        assert live.stop_reason == STOP_FINISHED
        n = _raw_count(tmp_path)
        time.sleep(0.4)
        assert _raw_count(tmp_path) == n
        assert live.mark_load_change().is_err


# frob:tests python/sadi/server/live.py::LiveAcquisition.check_once
def test_low_disk_stops_stream_with_fault(tmp_path: Path) -> None:
    """Free space under the floor stops the stream, sets a disk fault and blocks restart."""
    clock = _Clock()
    huge = 1 << 62
    with _session(tmp_path, clock, min_free_bytes=huge) as (_c, live):
        # Opened with the floor unreachable: never started.
        assert live.stop_reason == STOP_LOW_DISK
        assert not live.running
        assert live.mark_load_change().is_err
    wal_dir = next((tmp_path / "sessions").iterdir()) / "wal"
    assert wal_dir.exists()


# frob:tests python/sadi/server/live.py::LiveAcquisition.check_once
def test_low_disk_midrun_keeps_recorded_blocks(tmp_path: Path) -> None:
    """If space drops mid-run the stream stops and the fault names the disk."""
    clock = _Clock()
    with _session(tmp_path, clock) as (_c, live):
        time.sleep(0.4)
        live._min_free = 1 << 62  # noqa: SLF001
        live.check_once()
        assert live.stop_reason == STOP_LOW_DISK
        fault = live.fault
        assert fault is not None
        assert fault.origin == "disk"
        n = _raw_count(tmp_path)
        assert n > 0
        time.sleep(0.3)
        assert _raw_count(tmp_path) == n


# frob:tests python/sadi/core/device.py::free_bytes
def test_free_bytes_walks_to_existing_ancestor(tmp_path: Path) -> None:
    """A not-yet-created path reports the free space of its nearest existing parent."""
    got = free_bytes(tmp_path / "nope" / "deeper")
    assert got.is_ok
    assert got.danger_ok > 0
