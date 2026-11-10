"""Live acquisition for the served app: one device -> pipeline -> WAL -> bus run per open session.

The pipeline writes raw blocks to the open session's WAL (the same `WriterHandle` the session
service owns), so live data takes the normal durable path; nothing is displayed before it is
durable. With no session open nothing is read from the device and nothing is recorded. The run
also stops itself (draining every block already read into the WAL first) when the session is
finished, after an idle timeout with no point in progress, or when free disk space runs low;
nothing recorded is ever dropped or deleted. Device or
WAL faults are logged and kept on `LiveAcquisition.fault`; they never raise into the request path.
"""

# frob:ticket 01M6X572N6WB1053QZ1WV4W4WY
# frob:ticket 01M6X12VGS7NHWM3EZWF4YK7XN
# frob:ticket 01M723P32SR45XWMW7BE5QZE7H
# frob:ticket 01M724AKWJV8BRNRR3Q43553VR
from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final, cast

import numpy as np
from typani import Err, ErrorSet, Ok, Result

from sadi.api.acquisition import AcquisitionDriver, DriverFault
from sadi.bench.lctt_source import BOARD_FULL_SCALE_V
from sadi.core.device import DEVICE_RATE_HZ, LIVE_MIN_FREE_BYTES, StopFailed, free_bytes
from sadi.core.pipeline import (
    AcquisitionPipeline,
    Bus,
    PipelineConfig,
    PipelineError,
    PipelineStopped,
    ResultUpdate,
    SettleUpdate,
)
from sadi.labs.lctt.guidance import Phase
from sadi.labs.lctt.settle import SettleConfig
from sadi.labs.lctt.settle_stream import SettleState, StreamConfig
from sadi.logging_setup import get_logger
from sadi.store.records import SettingsV1

if TYPE_CHECKING:
    from pathlib import Path

    from sadi.core.device import DeviceService
    from sadi.core.errors import DeviceError
    from sadi.store.wal import Seq
    from sadi.store.writer_thread import WriterError, WriterHandle

_log = get_logger(__name__)

#: Analysis/display decimation: every Nth device sample is analysed (raw stays complete in WAL).
DECIMATE: Final[int] = 25
#: Bytes in one device packet (the pipeline's alignment check).
PACKET_LEN: Final[int] = 612
#: Simulator only: cumulative masses the panel instructs per load point, kg.
SIM_LOAD_TARGETS_KG: Final[tuple[float, ...]] = (0.075, 1.05, 2.325)
#: Simulator only: first (smallest) load step, kg; equals the first panel mass.
SIM_LOAD_STEP_KG: Final[float] = SIM_LOAD_TARGETS_KG[0]
#: Simulator only: SYNTHETIC mass hung per calibrate mark so the LVDT volts differ, kg.
#: The sim has no gauge blocks; this stands in for moving the core and is not a real height.
SIM_CAL_STEP_KG: Final[float] = 0.02
#: Phases in which a load-change mark means "more mass hung" (simulator load step).
_SIM_LOAD_PHASES: Final[frozenset[Phase | None]] = frozenset({Phase.ELASTIC, Phase.PLASTIC})
#: Default settle detector parameters (UNVERIFIED on real hardware; tune per lab).
# frob:ticket 01M71XGHCQP7KZ6HEFPJ2KEMF8
LIVE_SETTLE: Final[SettleConfig] = SettleConfig(
    window_s=0.5, threshold=0.05, min_dwell_s=0.5, min_points=10
)
#: Seconds with no load change and no unsettled point before raw streaming pauses.
IDLE_TIMEOUT_S: Final[float] = 600.0  # frob:ticket 01M723P32SR45XWMW7BE5QZE7H
#: How often the watchdog checks free space and idleness, seconds.
WATCH_POLL_S: Final[float] = 1.0
#: Stop reasons (`LiveAcquisition.stop_reason`).
STOP_FINISHED: Final[str] = "finished"
STOP_IDLE: Final[str] = "idle"
STOP_LOW_DISK: Final[str] = "low_disk"
#: A session is open but no board is attached yet (frob:ticket 01M724AKWJV8BRNRR3Q43553VR).
STOP_NO_DEVICE: Final[str] = "no_device"
#: Device statuses from which a stream can be started.
_READY_STATUSES: Final[frozenset[str]] = frozenset({"connected", "simulated"})


class LiveError(ErrorSet):
    """Why a live-run command was refused; the description is the hint shown to the operator."""

    NoLiveSession = "No acquisition is running; open or resume a session first"
    # frob:ticket 01M723P32SR45XWMW7BE5QZE7H
    LowDisk = "Free disk space is too low to record; free space, then reopen the session"
    Finished = "This session's acquisition was finished; resume the session to record again"
    # frob:ticket 01M724AKWJV8BRNRR3Q43553VR
    NoDevice = "No instrument is attached; plug in the SADI board and press Reconnect"


_CAPTURE_STOP_HINTS: Final[dict[str, str]] = {
    STOP_FINISHED: LiveError.Finished.description,
    STOP_LOW_DISK: LiveError.LowDisk.description,
    STOP_IDLE: "Recording is paused for idleness; press Resume live readings to start again",
    STOP_NO_DEVICE: LiveError.NoDevice.description,
}


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
        if got.is_err:
            err = got.danger_err
            kept = getattr(err, "blocks", None)
            if kept:  # keep the drained blocks on the error so the driver can still ingest them
                return Err(
                    StopFailed(
                        code=err.code,
                        detail=err.detail,
                        blocks=[_Decimated(b, self._step) for b in kept],
                    )
                )
        return got.map(lambda blocks: [_Decimated(b, self._step) for b in blocks])


class LiveAcquisition:
    """Starts a device-to-bus run when a session opens and stops it (draining) before it closes."""

    def __init__(  # noqa: PLR0913 - tunables are keyword-only knobs
        self,
        device: DeviceService,
        bus: Bus,
        settle: SettleConfig = LIVE_SETTLE,
        *,
        idle_timeout_s: float = IDLE_TIMEOUT_S,
        min_free_bytes: int = LIVE_MIN_FREE_BYTES,
        watch_poll_s: float = WATCH_POLL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
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
        self._idle_timeout_s = idle_timeout_s
        self._min_free = min_free_bytes
        self._watch_poll_s = watch_poll_s
        self._clock = clock
        self._phase_source: Callable[[], Phase | None] | None = None
        self._sim_load_marks = 0  # simulated load points hung so far (panel mass schedule)
        self._writer: WriterHandle | None = None
        self._path: Path | None = None
        self._stop_reason: str | None = None
        self._last_activity = clock()
        self._activity = bus.subscribe("live-activity")
        self._watch: threading.Thread | None = None
        self._watch_stop = threading.Event()

    @property
    def stop_reason(self) -> str | None:
        """Why raw streaming stopped while the session stayed open (finished/idle/low_disk)."""
        with self._lock:
            return self._stop_reason

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

    # frob:ticket 01M724AKWJV8BRNRR3Q43553VR
    @property
    def device_attached(self) -> bool:
        """True when the device can stream (connected or simulated), else False."""
        return str(self._device.status) in _READY_STATUSES

    # frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
    def set_phase_source(self, source: Callable[[], Phase | None]) -> None:
        """Wire the recorded run phase so a sim load step only happens in elastic/plastic."""
        self._phase_source = source

    # frob:ticket 01M724AKWJV8BRNRR3Q43553VR
    def capture_block_hint(self) -> str | None:
        """Why capture is blocked now (no device or stopped: finished/low_disk/idle), else None."""
        if not self.device_attached:
            return LiveError.NoDevice.description
        with self._lock:
            reason = self._stop_reason
        hint = _CAPTURE_STOP_HINTS.get(reason) if reason else None
        if hint is not None:
            _log.info("capture refused: stop_reason=%s", reason)
        return hint

    # frob:ticket 01M724AKWJV8BRNRR3Q43553VR
    def reconnect_device(self) -> Result[None, LiveError | DeviceError]:
        """Open (or reopen) the board and, if a session is open, start recording from it.

        Nothing already recorded is touched: the new run appends a fresh SETTINGS record and a
        new block sequence to the open session's WAL. A running healthy stream is left alone.
        """
        with self._lock:
            if self._driver is not None and self._driver.running and self.device_attached:
                _log.info("reconnect ignored: acquisition already running")
                return Ok(None)
            if self._driver is not None:
                _log.warning("reconnect: stopping faulted run first (blocks are drained)")
                _ = self._stop_run_locked(STOP_NO_DEVICE)
            res = self._device.reconnect()
            self._ingest_salvaged_locked()
            if res.is_err:
                _log.error("reconnect failed: %s", res.danger_err)
                return Err(res.danger_err)
            _log.info("device attached")
            if self._writer is None or self._path is None:
                return Ok(None)
            if self._stop_reason in (STOP_FINISHED, STOP_LOW_DISK):
                _log.info("device attached but session is %s; not streaming", self._stop_reason)
                return Ok(None)
            if self._low_disk_locked(self._path):
                self._stop_reason = STOP_LOW_DISK
                return Err(LiveError.LowDisk)
            self._start_run_locked(self._writer, self._path, record_settings=True)
            self._start_watch_locked()
            if self._pipe is None:
                return Err(LiveError.NoLiveSession)
            return Ok(None)

    # frob:ticket 01M7279606J0ZW8ZY1RZG2ZHS9
    def resume(self) -> Result[None, LiveError]:
        """Restart streaming after an idle pause without any load-change marker or sim load."""
        with self._lock:
            if self._pipe is not None:
                self._last_activity = self._clock()
                _log.info("resume: already streaming")
                return Ok(None)
            refused = self._resume_after_idle_locked()
            if refused is not None:
                _log.warning("resume refused: %s", refused.description)
                return Err(refused)
            self._last_activity = self._clock()
        _log.info("resumed streaming after idle (no marker written)")
        return Ok(None)

    # frob:ticket 01M7279606J0ZW8ZY1RZG2ZHS9
    def _ingest_salvaged_locked(self) -> None:
        """Write blocks a device teardown kept into the WAL before any new run starts."""
        kept = self._device.take_salvaged()
        if not kept:
            return
        if self._writer is None:
            _log.error("%d salvaged blocks have no open session to save into", len(kept))
            self._fault = DriverFault(origin="device", detail="Unsaved blocks could not be kept")
            return
        pipe = AcquisitionPipeline(self._writer, self._cfg, self.bus)
        pipe.start()
        saved = 0
        for block in kept:
            if pipe.ingest(_Decimated(block, DECIMATE)).is_ok:
                saved += 1
        pipe.stop()
        _log.warning("saved %d of %d salvaged blocks before reconnect", saved, len(kept))

    def mark_load_change(self) -> Result[Seq, LiveError | WriterError | PipelineError]:
        """Record a load-applied marker in the WAL and open a new settle point (Ok is its seq)."""
        with self._lock:
            if self._pipe is None:
                refused = self._resume_after_idle_locked()
                if refused is not None:
                    return Err(refused)
            pipe = self._pipe
            self._last_activity = self._clock()
        if pipe is None:
            _log.warning("load change refused: no live run")
            return Err(LiveError.NoLiveSession)
        self._apply_sim_load()
        return pipe.mark_load_change()

    # frob:ticket 01M723P32SR45XWMW7BE5QZE7H
    def _resume_after_idle_locked(self) -> LiveError | None:
        """Restart a run paused for idleness on a new load change; None means it is running."""
        if self._writer is None or self._path is None:
            return LiveError.NoLiveSession
        if self._stop_reason == STOP_FINISHED:
            return LiveError.Finished
        if self._stop_reason == STOP_LOW_DISK:
            return LiveError.LowDisk
        if self._stop_reason == STOP_NO_DEVICE:
            return LiveError.NoDevice
        if self._stop_reason != STOP_IDLE:
            return LiveError.NoLiveSession
        if not self.device_attached:
            _log.warning("resume after idle refused: device not attached")
            return LiveError.NoDevice
        if self._low_disk_locked(self._path):
            return LiveError.LowDisk
        _log.info("resuming raw streaming after idle for %s", self._path.name)
        self._start_run_locked(self._writer, self._path, record_settings=False)
        return None if self._pipe is not None else LiveError.NoLiveSession

    # frob:ticket 01M72ZNB9TN1CWMCK5G1J1H0BX
    def _next_sim_step(self) -> float:
        """Mass to add for the next load point so cumulative mass follows the panel masses."""
        targets = SIM_LOAD_TARGETS_KG
        i = self._sim_load_marks
        if i < len(targets):
            step = targets[i] - (targets[i - 1] if i else 0.0)
        else:
            step = targets[-1] - targets[-2]
        return round(step, 6)

    def _apply_sim_load(self) -> None:
        """On the simulator, hang one more step of mass so the next point has a new voltage.

        With a phase source wired, only the elastic and plastic phases hang the panel masses;
        a calibrate mark ("new gauge block") adds a small SYNTHETIC step so the LVDT volts
        differ, and the tare mark adds nothing.
        """  # frob:ticket 01M72ZNB9TN1CWMCK5G1J1H0BX
        step_kg = self._next_sim_step()
        is_cal = False
        if self._phase_source is not None:
            phase = self._phase_source()
            if phase is Phase.CALIBRATE:
                is_cal = True
                step_kg = SIM_CAL_STEP_KG
                _log.info("calibrate mark: synthetic LVDT step %.3f kg", step_kg)
            elif phase not in _SIM_LOAD_PHASES:
                _log.info("load change in phase %s: no simulated load step", phase)
                return
        if getattr(self._device, "is_synthetic", False):  # frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
            res = cast("Any", self._device).advance_load()
            if res.is_err:
                _log.warning("synthetic load step failed: %s", res.danger_err)
            return
        if not self._device.is_simulator:
            return
        res = self._device.sim_add_weight(step_kg)
        if res.is_err:
            _log.warning("simulated load step failed: %s", res.danger_err)
        elif not is_cal:
            self._sim_load_marks += 1

    def on_session_open(self, writer: WriterHandle, path: Path) -> None:
        """Start streaming into the new session WAL; failures are logged, not raised."""
        with self._lock:
            if self._driver is not None:
                _log.error("live run already active; not starting for %s", path.name)
                return
            self._writer = writer
            self._path = path
            self._stop_reason = None
            self._last_activity = self._clock()
            self._activity.drain()
            if self._low_disk_locked(path):
                self._stop_reason = STOP_LOW_DISK
                _log.error("not streaming for %s: free disk space too low", path.name)
                return
            if not self.device_attached:
                self._stop_reason = STOP_NO_DEVICE
                self._fault = DriverFault(origin="device", detail=LiveError.NoDevice.description)
                _log.warning("session %s open with no device; capture blocked", path.name)
                return
            self._start_run_locked(writer, path, record_settings=True)
            self._start_watch_locked()

    def _start_run_locked(self, writer: WriterHandle, path: Path, *, record_settings: bool) -> None:
        """Start pipeline, device and driver on `writer`; faults are kept, not raised."""
        pipe = AcquisitionPipeline(writer, self._cfg, self.bus)
        if record_settings:
            # frob:ticket 01M723P2Z9GC152RE82Y6JYAW5
            recorded = pipe.record_settings(self._settings_records())
            if recorded.is_err:
                self._fault = DriverFault(origin="pipeline", detail=str(recorded.danger_err))
                _log.error("settings not recorded for %s: %s", path.name, recorded.danger_err)
                return
        started = self._device.start_streaming()
        if started.is_err:
            self._fault = DriverFault(origin="device", detail=str(started.danger_err))
            _log.error("device start failed for %s: %s", path.name, started.danger_err)
            return
        self._fault = None
        driver = AcquisitionDriver(_DecimatingSource(self._device, DECIMATE), pipe)
        began = driver.start()
        if began.is_err:
            _log.error("driver start failed: %s", began.danger_err)
            self._device.stop_streaming()
            return
        self._driver = driver
        self._pipe = pipe
        self._stop_reason = None
        self._last_activity = self._clock()
        _log.info("live acquisition started for session %s", path.name)

    # frob:ticket 01M723P32SR45XWMW7BE5QZE7H
    def _low_disk_locked(self, path: Path) -> bool:
        """True when free space at `path` is below the floor; an unreadable probe is not low."""
        free = free_bytes(path)
        if free.is_err:
            return False
        if free.danger_ok < self._min_free:
            _log.error("free disk %d B below floor %d B", free.danger_ok, self._min_free)
            return True
        return False

    def stop_streaming(self, reason: str) -> Result[int, DriverFault]:
        """Stop raw streaming for `reason` but keep the session open.

        Every block already read is drained into the WAL first; the writer, the session and all
        recorded data are untouched. Ok is the number of trailing blocks saved.
        """
        with self._lock:
            return self._stop_run_locked(reason)

    def finish(self) -> Result[int, DriverFault]:
        """Stop raw streaming because the session is finished (Results/Export reached)."""
        return self.stop_streaming(STOP_FINISHED)

    def _stop_run_locked(self, reason: str) -> Result[int, DriverFault]:
        """Drain and stop the driver, remembering `reason`; Ok(0) when nothing was running."""
        driver, self._driver = self._driver, None
        self._pipe = None
        if driver is None:
            if self._stop_reason is None:
                self._stop_reason = reason
            return Ok(0)
        self._stop_reason = reason
        stopped = driver.stop()
        if stopped.is_err:
            fault = driver.fault or DriverFault(origin="driver", detail=str(stopped.danger_err))
            self._fault = fault
            _log.error("live acquisition stopped (%s) with fault: %s", reason, stopped.danger_err)
            return Err(fault)
        _log.info(
            "live acquisition stopped (%s); %d trailing blocks saved", reason, stopped.danger_ok
        )
        return Ok(stopped.danger_ok)

    def _start_watch_locked(self) -> None:
        """Start the idle/free-space watchdog once per session."""
        if self._watch is not None:
            return
        self._watch_stop.clear()
        self._watch = threading.Thread(target=self._watch_loop, name="sadi-live-watch")
        self._watch.start()

    def _watch_loop(self) -> None:
        """Poll free space and activity; stop raw streaming (never data) when warranted."""
        while not self._watch_stop.wait(self._watch_poll_s):
            self.check_once()

    def check_once(self) -> None:
        """One watchdog pass: stop on low disk, or on idleness with no point in progress."""
        events = self._activity.drain()
        with self._lock:
            now = self._clock()
            for ev in events:
                if isinstance(ev, ResultUpdate) or (
                    isinstance(ev, SettleUpdate)
                    and ev.status.point_index is not None
                    and ev.status.state != SettleState.SETTLED
                ):
                    self._last_activity = now
            if self._driver is None or self._path is None:
                return
            if self._low_disk_locked(self._path):
                if self._stop_run_locked(STOP_LOW_DISK).is_err:
                    _log.error("low-disk stop also faulted; recorded blocks remain")
                self._fault = DriverFault(
                    origin="disk",
                    detail="Free disk space is low; streaming stopped, recorded data is safe",
                )
                last = self._writer.durable_seq if self._writer is not None else 0
                self.bus.publish(
                    PipelineStopped(
                        reason=STOP_LOW_DISK,
                        hint="Free disk space, then reopen the session; saved data is safe",
                        last_durable_seq=last,
                    )
                )
                return
            if now - self._last_activity >= self._idle_timeout_s:
                _log.info(
                    "idle for %.0f s with no open point; pausing raw streaming",
                    now - self._last_activity,
                )
                if self._stop_run_locked(STOP_IDLE).is_err:
                    _log.error("idle stop ended with a fault: %s", self._fault)

    def _settings_records(self) -> list[SettingsV1]:
        """Settings needed to decode and rescale the raw packets later (docs/data-safety.md 2.2)."""
        if getattr(self._device, "is_synthetic", False):
            kind = "synthetic"
        else:
            kind = "simulator" if self._device.is_simulator else "real"
        rows: list[tuple[str, str, Any]] = [
            ("device", "adc_mode", "DLL_COMPATIBLE"),
            ("device", "adc_full_scale_v", BOARD_FULL_SCALE_V),
            ("device", "adc_code_bits", 16),
            ("device", "rate_hz", DEVICE_RATE_HZ),
            ("acquisition", "decimation", DECIMATE),
            ("acquisition", "packet_len", PACKET_LEN),
            ("device", "kind", kind),
            ("device", "firmware", getattr(self._device, "firmware", None) or "unknown"),
        ]
        return [SettingsV1(scope=a, key=b, value=c) for a, b, c in rows]

    def on_session_close(self) -> None:
        """Stop the run and drain its blocks into the WAL; must run before the writer closes."""
        self._watch_stop.set()
        watch, self._watch = self._watch, None
        if watch is not None:
            watch.join()
        with self._lock:
            had_run = self._driver is not None
            result = self._stop_run_locked("closed")
            self._stop_reason = None
            self._writer = None
            self._path = None
            if had_run and result.is_ok:
                _log.info("live acquisition closed with session")
