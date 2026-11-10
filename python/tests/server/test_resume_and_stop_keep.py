"""Resume after idle writes no marker; blocks survive a failed device stop and a teardown."""

# frob:ticket 01M7279606J0ZW8ZY1RZG2ZHS9
from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

import numpy as np
from typani import Err, Ok, Result

from sadi.api.acquisition import AcquisitionDriver
from sadi.core import device as dev
from sadi.core.errors import DeviceCode, DeviceError
from sadi.core.pipeline import AcquisitionPipeline, PipelineConfig, StreamConfig
from sadi.labs.lctt.settle import SettleConfig
from sadi.server.routes.acquisition import ResumeOut, resume_streaming
from sadi.store.records import RecordType
from sadi.store.wal import WalConfig, WalReader
from sadi.store.writer_thread import WriterHandle
from tests.server.test_idle_raw import _Clock, _raw_count, _session

N = 4
PACKET = 8


class _Block:
    def __init__(self) -> None:
        self.volts = np.full((N, 4), 1.0)
        self.n_samples = N
        self.raw = bytes(range(PACKET)) * N
        self.msg_count = np.arange(N, dtype=np.uint32)
        self.dropped_bytes = 0


class _FailingStop:
    """Source whose device stop fails but hands back the blocks it had already drained."""

    def next_block(self, timeout: float | None = 0.0) -> Result[Any, Any]:
        time.sleep(0.01)
        return Ok(None)

    def stop_streaming(self) -> Result[list[Any], Any]:
        return Err(
            dev.StopFailed(
                code=DeviceCode.DISCONNECTED, detail="cable out", blocks=[_Block(), _Block()]
            )
        )


class _BadStream:
    """Streaming stub whose stop command always fails."""

    def stop(self) -> Result[Any, DeviceError]:
        return Err(DeviceError(code=DeviceCode.DISCONNECTED, detail="port gone"))

    def force_close(self) -> Result[None, DeviceError]:
        return Ok(None)


def _types(root: Path) -> list[int]:
    wal_dir = next((root / "sessions").iterdir()) / "wal"
    return [int(r.danger_ok.type) for r in WalReader(wal_dir).records() if r.is_ok]


# frob:tests python/sadi/server/live.py::LiveAcquisition.resume
# frob:tests python/sadi/server/routes/acquisition.py::make_acquisition_router
# frob:tests python/sadi/server/routes/acquisition.py::resume_streaming
# frob:tests python/sadi/server/routes/acquisition.py::ResumeOut
def test_resume_after_idle_restarts_without_marker(tmp_path: Path) -> None:
    """POST /api/acquisition/resume restarts a paused run and writes no MARKER record."""
    clock = _Clock()
    with _session(tmp_path, clock, idle_timeout_s=10.0) as (c, live):
        time.sleep(0.4)
        clock.t = 11.0
        live.check_once()
        assert not live.running
        n = _raw_count(tmp_path)
        before = _types(tmp_path).count(RecordType.MARKER)
        got = c.post("/api/acquisition/resume")
        assert got.status_code == 200 and got.json() == {"streaming": True}
        assert live.running
        time.sleep(0.4)
        assert _raw_count(tmp_path) > n
        assert _types(tmp_path).count(RecordType.MARKER) == before
        assert c.post("/api/acquisition/resume").status_code == 200  # idempotent


def test_resume_refused_when_finished(tmp_path: Path) -> None:
    """A finished session is not restarted by resume: 409, nothing written."""
    with _session(tmp_path, _Clock()) as (c, live):
        assert live.finish().is_ok
        assert c.post("/api/acquisition/resume").status_code == 409
        assert not live.running


# frob:tests python/sadi/server/routes/acquisition.py::resume_streaming
def test_resume_without_live_acquisition_is_a_problem() -> None:
    """No wired live run gives an Err problem, never an exception."""
    assert resume_streaming(None).is_err
    assert resume_streaming(lambda: Ok(None)) == Ok(ResumeOut(streaming=True))


# frob:tests python/sadi/api/acquisition.py::AcquisitionDriver.stop
def test_driver_ingests_drained_blocks_before_reporting_stop_fault(tmp_path: Path) -> None:
    """A failed device stop still writes its drained blocks, then reports the fault."""
    wal = tmp_path / "wal"
    wal.mkdir()
    opened = WriterHandle.open(wal, uuid.UUID(int=7), 1, WalConfig())
    assert opened.is_ok
    settle = SettleConfig(window_s=0.05, threshold=1.0, min_dwell_s=0.05, min_points=5)
    cfg = PipelineConfig(
        stream=StreamConfig(settle=settle), sample_rate_hz=1000.0, packet_len=PACKET
    )
    drv = AcquisitionDriver(
        _FailingStop(), AcquisitionPipeline(opened.danger_ok, cfg), tick_interval_s=0.01
    )
    assert drv.start().is_ok
    stopped = drv.stop()
    assert stopped.is_err and "cable out" in stopped.danger_err.detail
    assert drv.ingested == 2
    opened.danger_ok.close()
    raw = [
        r
        for r in WalReader(wal).records()
        if r.is_ok and r.danger_ok.type == int(RecordType.RAW_BLOCK)
    ]
    assert len(raw) == 2


# frob:tests python/sadi/core/device.py::DeviceService.stop_streaming
# frob:tests python/sadi/core/device.py::StopFailed
def test_stop_streaming_error_carries_drained_blocks() -> None:
    """When the stop command fails the Err still holds every queued block."""
    svc = dev.DeviceService(dev.DeviceSource(kind="sim", scenario="clean", seed=1))
    assert svc.open().is_ok
    svc._streaming = _BadStream()  # type: ignore[assignment]  # noqa: SLF001
    svc._queue.put(_Block())  # type: ignore[arg-type]  # noqa: SLF001
    svc._queue.put(_Block())  # type: ignore[arg-type]  # noqa: SLF001
    res = svc.stop_streaming()
    assert res.is_err
    err = res.danger_err
    assert isinstance(err, dev.StopFailed) and len(err.blocks) == 2
    assert err.code == DeviceCode.DISCONNECTED
    svc._streaming = None  # noqa: SLF001
    svc.close()


# frob:tests python/sadi/core/device.py::DeviceService.take_salvaged
def test_teardown_keeps_queued_blocks_for_the_caller() -> None:
    """Reconnect/close teardown hands queued blocks back instead of discarding them."""
    svc = dev.DeviceService(dev.DeviceSource(kind="sim", scenario="clean", seed=1))
    assert svc.open().is_ok
    svc._queue.put(_Block())  # type: ignore[arg-type]  # noqa: SLF001
    svc.close()
    kept = svc.take_salvaged()
    assert len(kept) == 1
    assert svc.take_salvaged() == []
