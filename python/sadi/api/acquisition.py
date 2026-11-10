"""Acquisition driver: device blocks -> pipeline, health tick timer and the load chain.

Wires `AcquisitionPipeline` (docs/core/pipeline.md) to a block source and the API layer. Every
block the source yields goes through `pipeline.ingest`, hence the WAL; on stop the source's
trailing blocks are ingested too, so nothing is dropped. A fault stops the loop loudly and is
kept on `AcquisitionDriver.fault`. Description: docs/api/acquisition.md.
"""

# frob:ticket 01M6WJT055W0QPZYNF862E6T8C
from __future__ import annotations

import threading
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field
from typani import Err, ErrorSet, Ok, Result, propagate

from sadi.core.errors import DeviceError
from sadi.core.events import PointWindow
from sadi.core.pipeline import AcquisitionPipeline, BlockLike, PipelineError
from sadi.core.point_inputs import PointInputs, PointMeta, build_point
from sadi.logging_setup import get_logger
from sadi.store.writer_thread import WriterError

_log = get_logger(__name__)

#: Default seconds between pipeline health checks.
DEFAULT_TICK_INTERVAL_S = 0.5
#: Default seconds the acquire loop waits for a block before re-checking for stop.
DEFAULT_POLL_S = 0.2
_JOIN_TIMEOUT_S = 10.0


class AcquisitionError(ErrorSet):
    """Driver refusals; the description says what to do."""

    AlreadyRunning = "Acquisition is already running"
    NotRunning = "Acquisition is not running"
    ChainExhausted = "Every load step in the chain has been applied"
    NoChain = "No load chain is configured"


class BlockSource(Protocol):
    """The slice of `DeviceService` the driver uses (typed `DeviceError` failures)."""

    def next_block(self, timeout: float | None = ...) -> Result[Any, DeviceError]:
        """Pop the next block (Ok(None) on timeout) or return the device fault."""
        ...

    def stop_streaming(self) -> Result[list[Any], DeviceError]:
        """Stop the device; return blocks still queued plus the trailing block."""
        ...


class DriverFault(BaseModel):
    """Why the acquire loop stopped; raw data already saved is unaffected."""

    model_config = ConfigDict(frozen=True)

    origin: str
    detail: str


class LoadStep(BaseModel):
    """One step of the load chain: a label and the applied mass in kilograms."""

    model_config = ConfigDict(frozen=True)

    label: str
    mass_kg: float = Field(ge=0)


class LoadChain(BaseModel):
    """Ordered load steps with a cursor; `applied` counts steps whose marker was written."""

    steps: tuple[LoadStep, ...]
    applied: int = 0

    def peek(self) -> LoadStep | None:
        """Return the next unapplied step, or None when the chain is done."""
        return self.steps[self.applied] if self.applied < len(self.steps) else None


class AcquisitionDriver:
    """Runs the acquire loop and tick timer threads around one pipeline and block source."""

    def __init__(
        self,
        source: BlockSource,
        pipeline: AcquisitionPipeline,
        *,
        chain: LoadChain | None = None,
        tick_interval_s: float = DEFAULT_TICK_INTERVAL_S,
        poll_s: float = DEFAULT_POLL_S,
    ) -> None:
        """Wire the driver; nothing runs until `start`."""
        self._source = source
        self._pipe = pipeline
        self._chain = chain
        self._tick_s = tick_interval_s
        self._poll_s = poll_s
        self._lock = threading.Lock()
        self._fault: DriverFault | None = None
        self._ingested = 0
        self._stop = threading.Event()
        self._acq: threading.Thread | None = None
        self._ticker: threading.Thread | None = None

    @property
    def fault(self) -> DriverFault | None:
        """The first fault that stopped acquisition, if any."""
        with self._lock:
            return self._fault

    @property
    def ingested(self) -> int:
        """Blocks handed to the WAL so far."""
        with self._lock:
            return self._ingested

    @property
    def running(self) -> bool:
        """True while the acquire loop thread is alive."""
        return self._acq is not None and self._acq.is_alive()

    def start(self) -> Result[None, AcquisitionError]:
        """Start the forwarder, the acquire loop and the tick timer."""
        if self._acq is not None:
            return Err(AcquisitionError.AlreadyRunning)
        self._stop.clear()
        self._pipe.start()
        self._acq = threading.Thread(target=self._acquire_loop, name="sadi-acquire")
        self._ticker = threading.Thread(target=self._tick_loop, name="sadi-tick")
        self._acq.start()
        self._ticker.start()
        _log.info("acquisition driver started (tick %.3g s)", self._tick_s)
        return Ok(None)

    def stop(self) -> Result[int, AcquisitionError | DriverFault]:
        """Stop the loops, ingest the device's trailing blocks (even if its stop failed), drain the pipeline.

        Returns the number of trailing blocks ingested; a device stop error is returned as a
        `DriverFault` (blocks already ingested stay saved).
        """
        if self._acq is None:
            return Err(AcquisitionError.NotRunning)
        self._stop.set()
        self._acq.join(_JOIN_TIMEOUT_S)
        if self._ticker is not None:
            self._ticker.join(_JOIN_TIMEOUT_S)
        self._acq = self._ticker = None
        res = self._source.stop_streaming()
        # A failed stop may still carry the blocks already read; they are saved before the fault.
        blocks = list(getattr(res.danger_err, "blocks", ())) if res.is_err else res.danger_ok
        tail = 0
        for block in blocks:
            if block is None or not int(block.n_samples):
                continue
            if self._ingest(block) is not None:
                break
            tail += 1
        if res.is_err:
            fault = DriverFault(origin="device", detail=str(res.danger_err))
            self._record_fault(fault)
            self._pipe.stop()
            _log.error("device stop failed; %d drained blocks ingested first", tail)
            return Err(fault)
        self._pipe.stop()
        _log.info("acquisition driver stopped; %d trailing blocks ingested", tail)
        return Ok(tail)

    def next_load(self) -> Result[LoadStep, AcquisitionError | WriterError | PipelineError]:
        """Write a load-applied marker for the next chain step and advance the cursor.

        The cursor only advances after the marker is accepted, so a refusal skips nothing.
        """
        if self._chain is None:
            return Err(AcquisitionError.NoChain)
        step = self._chain.peek()
        if step is None:
            return Err(AcquisitionError.ChainExhausted)
        res = self._pipe.mark_load_change()
        if res.is_err:
            _log.error("load step %r refused: %s", step.label, res.danger_err)
            return Err(res.danger_err)
        self._chain.applied += 1
        _log.info(
            "load step %r (%.6g kg) applied, marker seq=%d", step.label, step.mass_kg, res.danger_ok
        )
        return Ok(step)

    @propagate
    def record_point(
        self, inputs: PointInputs, window: PointWindow, meta: PointMeta | None = None
    ) -> Result[str, WriterError | PipelineError]:
        """Write a POINT event (inputs plus settle meta) in the shared mapping; Ok is its id."""
        point = build_point(inputs, window, meta)
        res = self._pipe.record_point(point)
        res.unwrap()
        return Ok(point.point_id)

    def _record_fault(self, fault: DriverFault) -> None:
        """Keep the first fault and log every one loudly."""
        _log.error("acquisition fault (%s): %s", fault.origin, fault.detail)
        with self._lock:
            if self._fault is None:
                self._fault = fault

    def _ingest(self, block: BlockLike) -> DriverFault | None:
        """Send one block to the WAL via the pipeline; a refusal is recorded and returned."""
        res = self._pipe.ingest(block)
        if res.is_err:
            fault = DriverFault(origin="pipeline", detail=str(res.danger_err))
            self._record_fault(fault)
            return fault
        with self._lock:
            self._ingested += 1
        return None

    def _acquire_loop(self) -> None:
        """Move blocks from the source into the pipeline until stopped or faulted."""
        while not self._stop.is_set():
            res = self._source.next_block(self._poll_s)
            if res.is_err:
                self._record_fault(DriverFault(origin="device", detail=str(res.danger_err)))
                self._halt_pipeline()
                return
            block = res.danger_ok
            if block is None:
                continue
            if self._ingest(block) is not None:
                return

    # frob:ticket 01M6WMVRTG5YQDSZYQQG368G2E
    def _halt_pipeline(self) -> None:
        """Make a device fault visible to the display through the pipeline's loud halt."""
        self._pipe.halt("device_fault", "Check the device connection; saved data is safe")

    def _tick_loop(self) -> None:
        """Run the pipeline health check every tick interval until stopped."""
        while not self._stop.wait(self._tick_s):
            res = self._pipe.tick()
            if res.is_err:
                self._record_fault(DriverFault(origin="wal", detail=str(res.danger_err)))
                self._stop.set()
                return
