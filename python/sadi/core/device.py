"""DeviceService: open simulator or serial board, stream blocks via a reader thread, reconnect."""

# frob:ticket 01M6W7R2NWFTQBK7FRWGX511CP

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Final, Literal

import sadi_py as sp
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.core.errors import DeviceCode, DeviceError
from sadi.core.phases import (
    Connected,
    Disconnected,
    Stopped,
    Streaming,
    list_ports,
    open_serial,
    open_sim,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

#: USB vendor id of FTDI, the bridge chip on the SADI board.
FTDI_VID: Final[int] = 0x0403
#: Default bounded reader queue depth, in blocks (concurrency.md section 3).
DEFAULT_QUEUE_BLOCKS: Final[int] = 256
_JOIN_TIMEOUT_S: Final[float] = 5.0


class DeviceStatus(StrEnum):
    """Coarse device state shown in the UI."""

    CONNECTED = "connected"
    SIMULATED = "simulated"
    ERROR = "error"


class DeviceSource(BaseModel):
    """Where blocks come from: the simulator, or a serial port (None = auto-detect FTDI)."""

    model_config = ConfigDict(frozen=True)

    kind: Literal["sim", "serial"] = "sim"
    scenario: str = "clean"
    seed: int | None = None
    port: str | None = None


class ReaderOverflow(BaseModel):
    """The consumer fell behind and the bounded queue filled; no block was dropped."""

    model_config = ConfigDict(frozen=True)

    capacity: int
    detail: str = ""

    @property
    def hint(self) -> str:
        """User-facing 'what to do' text."""
        return "Processing fell behind the board; stop and restart streaming. Raw data is safe."


class Backoff(BaseModel):
    """Reconnect schedule: delay = min(base_s * 2**attempt, max_s) between `attempts` tries."""

    model_config = ConfigDict(frozen=True)

    attempts: int = 5
    base_s: float = 0.2
    max_s: float = 5.0

    def delay(self, attempt: int) -> float:
        """Seconds to wait after the given zero-based failed attempt."""
        return min(self.base_s * (2**attempt), self.max_s)


DeviceFault = DeviceError | ReaderOverflow


class DeviceService:
    """Owns one device session; reader thread feeds a bounded queue consumed via next_block."""

    def __init__(
        self,
        source: DeviceSource,
        *,
        queue_blocks: int = DEFAULT_QUEUE_BLOCKS,
        backoff: Backoff | None = None,
        sleep: Callable[[float], None] = time.sleep,
        cfg: sp.SessionConfig | None = None,
    ) -> None:
        """Create a closed service; call open() to connect."""
        self._source = source
        self._capacity = queue_blocks
        self._backoff = backoff or Backoff()
        self._sleep = sleep
        self._cfg = cfg
        self._lock = threading.RLock()
        self._connected: Connected | None = None
        self._streaming: Streaming | None = None
        self._queue: queue.Queue[sp.Block] = queue.Queue(maxsize=queue_blocks)
        self._fault: DeviceFault | None = None
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None
        self._errored = False
        self._held: sp.Block | None = None

    @property
    def status(self) -> DeviceStatus:
        """connected, simulated (sim source up), or error (open failed or reader faulted)."""
        with self._lock:
            idle = self._connected is None and self._streaming is None
            if self._errored or self._fault is not None or idle:
                return DeviceStatus.ERROR
            return DeviceStatus.SIMULATED if self._source.kind == "sim" else DeviceStatus.CONNECTED

    @property
    def fault(self) -> DeviceFault | None:
        """The error that stopped the reader, if any."""
        with self._lock:
            return self._fault

    def open(self) -> Result[None, DeviceError]:
        """Open the source and run the handshake once; Err sets status to error."""
        with self._lock:
            if self._connected is not None or self._streaming is not None:
                raise RuntimeError("DeviceService.open called while already open")
            res = self._open_once()
            if isinstance(res, Err):
                self._errored = True
                _log.error("device open failed: %s", res.danger_err.detail)
                return Err(res.danger_err)
            self._connected = res.danger_ok
            self._errored = False
            self._fault = None
            _log.info("device open (%s)", self._source.kind)
            return Ok(None)

    def reconnect(self) -> Result[None, DeviceError]:
        """Tear down any session and reopen with exponential backoff; Err after the last try."""
        with self._lock:
            self._teardown()
            last: DeviceError | None = None
            for attempt in range(self._backoff.attempts):
                res = self._open_once()
                if isinstance(res, Ok):
                    self._connected = res.danger_ok
                    self._errored = False
                    self._fault = None
                    _log.info("reconnected on attempt %d", attempt + 1)
                    return Ok(None)
                last = res.danger_err
                delay = self._backoff.delay(attempt)
                _log.warning(
                    "reconnect attempt %d/%d failed (%s); retry in %.2fs",
                    attempt + 1,
                    self._backoff.attempts,
                    last.detail,
                    delay,
                )
                if attempt + 1 < self._backoff.attempts:
                    self._sleep(delay)
            self._errored = True
            _log.error("reconnect gave up after %d attempts", self._backoff.attempts)
            return Err(last or DeviceError(code=DeviceCode.NOT_FOUND, detail="no attempts made"))

    def start_streaming(
        self, adc_mode: sp.AdcMode = sp.AdcMode.DLL_COMPATIBLE
    ) -> Result[None, DeviceError]:
        """Start the device and the reader thread."""
        with self._lock:
            if self._connected is None:
                raise RuntimeError("start_streaming requires an open, non-streaming service")
            conn = self._connected
            res = conn.start(adc_mode)
            if isinstance(res, Err):
                self._errored = True
                return Err(res.danger_err)
            streaming = res.danger_ok
            self._connected = None
            self._streaming = streaming
            self._fault = None
            self._stop_evt.clear()
            self._thread = threading.Thread(
                target=self._reader, args=(streaming,), name="sadi-reader", daemon=True
            )
            self._thread.start()
            _log.info("reader thread started (queue=%d blocks)", self._capacity)
            return Ok(None)

    def next_block(self, timeout: float | None = 1.0) -> Result[sp.Block | None, DeviceFault]:
        """Pop the next queued block (None on timeout); queued blocks drain before a fault shows."""
        try:
            return Ok(self._queue.get(timeout=timeout))
        except queue.Empty:
            with self._lock:
                held = self._held
                self._held = None
                fault = self._fault
            if held is not None:
                return Ok(held)
            if fault is not None:
                return Err(fault)
            return Ok(None)

    def stop_streaming(self) -> Result[list[sp.Block], DeviceError]:
        """Stop the reader and the device; returns blocks still queued plus the trailing block."""
        with self._lock:
            streaming = self._streaming
            if streaming is None:
                raise RuntimeError("stop_streaming requires a streaming service")
            self._join_reader()
            pending: list[sp.Block] = []
            while True:
                try:
                    pending.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            if self._held is not None:
                pending.append(self._held)
                self._held = None
            res = streaming.stop()
            if isinstance(res, Err):
                self._errored = True
                return Err(res.danger_err)
            stopped, tail = res.danger_ok
            self._streaming = None
            pending.append(tail)
            return self._back_to_connected(stopped).map(lambda _: pending)

    def close(self) -> None:
        """Best-effort shutdown of reader and session; safe to call in any state."""
        with self._lock:
            self._teardown()
            self._errored = False
            _log.info("device service closed")

    def _back_to_connected(self, stopped: Stopped) -> Result[None, DeviceError]:
        """Restart a Stopped session into Connected so streaming can begin again."""
        res = stopped.restart()
        if isinstance(res, Err):
            self._errored = True
            return Err(res.danger_err)
        self._connected = res.danger_ok
        return Ok(None)

    def _open_once(self) -> Result[Connected, DeviceError]:
        """Open the configured source and connect; closes a half-opened session on failure."""
        if self._source.kind == "sim":
            opened = open_sim(self._source.scenario, self._source.seed, self._cfg)
        else:
            opened = self._resolve_port().and_then(lambda p: open_serial(p, self._cfg))
        if isinstance(opened, Err):
            return Err(opened.danger_err)
        return self._connect(opened.danger_ok)

    @staticmethod
    def _connect(disc: Disconnected) -> Result[Connected, DeviceError]:
        """Handshake; on failure release the port so a retry can reopen it."""
        res = disc.connect()
        if isinstance(res, Err):
            closed = disc.close()
            if isinstance(closed, Err):
                _log.warning("close after failed connect also failed: %s", closed.danger_err.detail)
        return res

    def _resolve_port(self) -> Result[str, DeviceError]:
        """Return the configured port or auto-detect the first FTDI device."""
        if self._source.port is not None:
            return Ok(self._source.port)
        listed = list_ports()
        if isinstance(listed, Err):
            return Err(listed.danger_err)
        ftdi = [p for p in listed.danger_ok if p.vid == FTDI_VID]
        if not ftdi:
            _log.error("no FTDI serial port found among %d ports", len(listed.danger_ok))
            return Err(DeviceError(code=DeviceCode.NOT_FOUND, detail="no FTDI serial port found"))
        if len(ftdi) > 1:
            _log.warning("%d FTDI ports found; using %s", len(ftdi), ftdi[0].name)
        return Ok(ftdi[0].name)

    def _reader(self, streaming: Streaming) -> None:
        """Reader thread: read blocks into the bounded queue; stop loudly on error or overflow."""
        while not self._stop_evt.is_set():
            res = streaming.read_block()
            match res:
                case Err(err):
                    _log.error("reader stopping on device error: %s", err.detail)
                    self._set_fault(err)
                    return
                case Ok(block):
                    try:
                        self._queue.put_nowait(block)
                    except queue.Full:
                        _log.error(
                            "reader queue full (%d blocks); stopping, nothing dropped",
                            self._capacity,
                        )
                        with self._lock:
                            self._held = block
                        self._set_fault(
                            ReaderOverflow(
                                capacity=self._capacity,
                                detail="consumer too slow; reader stopped, the last block is kept",
                            )
                        )
                        return
        _log.debug("reader thread exiting on stop request")

    def _set_fault(self, fault: DeviceFault) -> None:
        """Record the first fault that ended the reader."""
        with self._lock:
            if self._fault is None:
                self._fault = fault

    def _join_reader(self) -> None:
        """Signal the reader to stop and wait for it."""
        self._stop_evt.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=_JOIN_TIMEOUT_S)
            if thread.is_alive():
                _log.error("reader thread did not exit within %.1fs", _JOIN_TIMEOUT_S)
            self._thread = None

    def _teardown(self) -> None:
        """Stop the reader and close whichever phase object is live."""
        self._join_reader()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._held = None
        if self._streaming is not None:
            stopped = self._streaming.stop()
            self._streaming = None
            if isinstance(stopped, Ok):
                self._log_close(stopped.danger_ok[0].close())
        if self._connected is not None:
            self._log_close(self._connected.close())
            self._connected = None

    @staticmethod
    def _log_close(res: Result[None, DeviceError]) -> None:
        """Log a close failure; teardown continues regardless."""
        if isinstance(res, Err):
            _log.warning("close failed during teardown: %s", res.danger_err.detail)
