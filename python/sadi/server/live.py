"""Live acquisition for the served app: one device -> pipeline -> WAL -> bus run per open session.

The pipeline writes raw blocks to the open session's WAL (the same `WriterHandle` the session
service owns), so live data takes the normal durable path; nothing is displayed before it is
durable. With no session open nothing is read from the device and nothing is recorded. Device or
WAL faults are logged and kept on `LiveAcquisition.fault`; they never raise into the request path.
"""

# frob:ticket 01M6X572N6WB1053QZ1WV4W4WY
# frob:ticket 01M6X12VGS7NHWM3EZWF4YK7XN
from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Final, cast

import numpy as np
from typani import Err, ErrorSet, Result

from sadi.api.acquisition import AcquisitionDriver, DriverFault
from sadi.core.pipeline import AcquisitionPipeline, Bus, PipelineConfig, PipelineError
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import StreamConfig
from sadi.logging_setup import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from sadi.core.device import DeviceService
    from sadi.store.wal import Seq
    from sadi.store.writer_thread import WriterError, WriterHandle

_log = get_logger(__name__)

#: Device sample rate of the SADI board and simulator, Hz.
DEVICE_RATE_HZ: Final[float] = 50_000.0
#: Analysis/display decimation: every Nth device sample is analysed (raw stays complete in WAL).
DECIMATE: Final[int] = 25
#: Bytes in one device packet (the pipeline's alignment check).
PACKET_LEN: Final[int] = 612
#: Simulator only: mass hung on each load-change so successive points differ, kg.
SIM_LOAD_STEP_KG: Final[float] = 0.1
#: Default settle detector parameters (UNVERIFIED on real hardware; tune per lab).
# frob:ticket 01M71XGHCQP7KZ6HEFPJ2KEMF8
LIVE_SETTLE: Final[SettleConfig] = SettleConfig(
    window_s=0.5, threshold=0.05, min_dwell_s=0.5, min_points=10
)


class LiveError(ErrorSet):
    """Why a live-run command was refused; the description is the hint shown to the operator."""

    NoLiveSession = "No acquisition is running; open or resume a session first"


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
        self._pipe: AcquisitionPipeline | None = None
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

    def mark_load_change(self) -> Result[Seq, LiveError | WriterError | PipelineError]:
        """Record a load-applied marker in the WAL and open a new settle point (Ok is its seq)."""
        with self._lock:
            pipe = self._pipe
        if pipe is None:
            _log.warning("load change refused: no live run")
            return Err(LiveError.NoLiveSession)
        self._apply_sim_load()
        return pipe.mark_load_change()

    def _apply_sim_load(self) -> None:
        """On the simulator, hang one more step of mass so the next point has a new voltage."""
        if getattr(self._device, "is_synthetic", False):  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
            res = cast("Any", self._device).advance_load()
            if res.is_err:
                _log.warning("synthetic load step failed: %s", res.danger_err)
            return
        if not self._device.is_simulator:
            return
        res = self._device.sim_add_weight(SIM_LOAD_STEP_KG)
        if res.is_err:
            _log.warning("simulated load step failed: %s", res.danger_err)

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
            self._pipe = pipe
            _log.info("live acquisition started for session %s", path.name)

    def on_session_close(self) -> None:
        """Stop the run and drain its blocks into the WAL; must run before the writer closes."""
        with self._lock:
            driver, self._driver = self._driver, None
            self._pipe = None
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
