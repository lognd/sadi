"""Live acquisition for the served app: one device -> pipeline -> WAL -> bus run per open session.

The pipeline writes raw blocks to the open session's WAL (the same `WriterHandle` the session
service owns), so live data takes the normal durable path; nothing is displayed before it is
durable. With no session open nothing is read from the device and nothing is recorded. Device or
WAL faults are logged and kept on `LiveAcquisition.fault`; they never raise into the request path.
"""

# frob:ticket 01M6X12VGS7NHWM3EZWF4YK7XN
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Final

import numpy as np
from typani import Result

from sadi.api.acquisition import AcquisitionDriver, DriverFault
from sadi.core.pipeline import AcquisitionPipeline, Bus, PipelineConfig
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import StreamConfig
from sadi.logging_setup import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from sadi.core.device import DeviceService
    from sadi.store.writer_thread import WriterHandle

_log = get_logger(__name__)

#: Device sample rate of the SADI board and simulator, Hz.
DEVICE_RATE_HZ: Final[float] = 50_000.0
#: Analysis/display decimation: every Nth device sample is analysed (raw stays complete in WAL).
DECIMATE: Final[int] = 25
#: Bytes in one device packet (the pipeline's alignment check).
PACKET_LEN: Final[int] = 612
#: Default settle detector parameters (UNVERIFIED on real hardware; tune per lab).
LIVE_SETTLE: Final[SettleConfig] = SettleConfig(
    window_s=0.02, threshold=1.0, min_dwell_s=0.03, min_points=5
)


class _Decimated:
    """A device block seen through analysis decimation; `raw` is kept whole for the WAL."""

    def __init__(self, block: Any, step: int) -> None:
        """Wrap `block`, keeping every `step`-th analysis sample."""
        self.raw = bytes(block.raw)
        self.volts = np.asarray(block.volts)[::step]
        self.msg_count = np.asarray(block.msg_count)[::step]
        self.n_samples = int(self.volts.shape[0])
        self.dropped_bytes = int(block.dropped_bytes)


class _DecimatingSource:
    """Block source adapter handing the driver decimated views of the device's blocks."""

    def __init__(self, device: DeviceService, step: int) -> None:
        """Adapt `device`, decimating by `step`."""
        self._device = device
        self._step = step

    def next_block(self, timeout: float | None = 1.0) -> Result[Any, Any]:
        """Next decimated block (Ok(None) on timeout) or the device fault."""
        got = self._device.next_block(timeout)
        return got.map(lambda b: None if b is None else _Decimated(b, self._step))

    def stop_streaming(self) -> Result[list[Any], Any]:
        """Stop the device; trailing blocks come back decimated."""
        got = self._device.stop_streaming()
        return got.map(lambda blocks: [_Decimated(b, self._step) for b in blocks])


class LiveAcquisition:
    """Starts a device-to-bus run when a session opens and stops it (draining) before it closes."""

    def __init__(self, device: DeviceService, bus: Bus, settle: SettleConfig = LIVE_SETTLE) -> None:
        """Hold the opened `device` and the `bus` the WebSocket hub subscribes to."""
        self._device = device
        self.bus = bus
        self._cfg = PipelineConfig(
            stream=StreamConfig(settle=settle),
            sample_rate_hz=DEVICE_RATE_HZ / DECIMATE,
            packet_len=PACKET_LEN,
        )
        self._lock = threading.Lock()
        self._driver: AcquisitionDriver | None = None
        self._fault: DriverFault | None = None

    @property
    def fault(self) -> DriverFault | None:
        """The first fault of the current or last run, if any (surfaced to the operator)."""
        with self._lock:
            if self._fault is not None:
                return self._fault
            return self._driver.fault if self._driver is not None else None

    @property
    def running(self) -> bool:
        """True while a run is active."""
        with self._lock:
            return self._driver is not None and self._driver.running

    def on_session_open(self, writer: WriterHandle, path: Path) -> None:
        """Start streaming into the new session WAL; failures are logged, not raised."""
        with self._lock:
            if self._driver is not None:
                _log.error("live run already active; not starting for %s", path.name)
                return
            started = self._device.start_streaming()
            if started.is_err:
                self._fault = DriverFault(origin="device", detail=str(started.danger_err))
                _log.error("device start failed for %s: %s", path.name, started.danger_err)
                return
            self._fault = None
            pipe = AcquisitionPipeline(writer, self._cfg, self.bus)
            driver = AcquisitionDriver(_DecimatingSource(self._device, DECIMATE), pipe)
            began = driver.start()
            if began.is_err:
                _log.error("driver start failed: %s", began.danger_err)
                self._device.stop_streaming()
                return
            self._driver = driver
            _log.info("live acquisition started for session %s", path.name)

    def on_session_close(self) -> None:
        """Stop the run and drain its blocks into the WAL; must run before the writer closes."""
        with self._lock:
            driver, self._driver = self._driver, None
            if driver is None:
                return
            stopped = driver.stop()
            if stopped.is_err:
                self._fault = driver.fault or DriverFault(
                    origin="driver", detail=str(stopped.danger_err)
                )
                _log.error("live acquisition stopped with fault: %s", stopped.danger_err)
                return
            _log.info("live acquisition stopped (%d trailing blocks saved)", stopped.danger_ok)
