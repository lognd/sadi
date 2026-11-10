"""LCTT capture modes: human confirm, auto-capture with max wait, fixed dwell, forced-early."""

# frob:ticket 01M6W7R06C7F7ZN0RC4CV3NWW5

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator
from typani import Err, ErrorSet, Ok, Result

# frob:ticket 01M6WJPHV1FMFMMRZ9WXZE3GBF
from sadi.core.events import EditV1, PointV1, PointWindow

# frob:ticket 01M6WNEEBBBZVDZ6700RJDN26D
from sadi.core.point_inputs import LoadInputs, PointMeta, build_point
from sadi.labs.lctt.settle import SettleError
from sadi.labs.lctt.settle_stream import (
    PointRecord,
    SettleMode,
    SettleState,
    StreamConfig,
    StreamError,
    StreamingSettleDetector,
    StreamStatus,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

Clock = Callable[[], float]
"""Monotonic seconds source; injected so tests are deterministic."""

RawRangeResolver = Callable[[float, float], PointWindow | None]
"""Maps an averaging window (start_t, end_t) to the raw WAL seq range it covers."""


class CaptureError(ErrorSet):
    """Capture misuse or an unresolvable raw range; the description says what to fix."""

    NoOpenPoint = "No open point; start a point (load change) before capturing"
    ModeMismatch = "fixed_dwell capture needs a StreamConfig in fixed_dwell mode, and only then"
    NoRawRange = "No raw WAL seq range covers the averaging window; flush raw before capturing"


class CaptureMode(StrEnum):
    """How a point is captured."""

    CONFIRM = "confirm"
    AUTO = "auto"
    FIXED_DWELL = "fixed_dwell"


class CaptureConfig(BaseModel):
    """Frozen capture parameters: mode, phase label and the auto-mode maximum wait."""

    model_config = {"frozen": True}

    mode: CaptureMode = CaptureMode.CONFIRM
    phase: str = Field(min_length=1, description="Run phase recorded on each point")
    max_wait_s: float | None = Field(
        default=None, gt=0, le=86400, description="Auto mode: force-capture after this wait, s"
    )

    @model_validator(mode="after")
    def _need_max_wait(self) -> CaptureConfig:
        """Auto mode requires max_wait_s."""
        if self.mode is CaptureMode.AUTO and self.max_wait_s is None:
            raise ValueError("max_wait_s is required when mode is auto")
        return self


class Captured(BaseModel):
    """A captured point event, its load inputs, detector record and operator-facing warnings.

    Record it with
    `AcquisitionDriver.record_point(captured.inputs, captured.point.window, captured.meta)`.
    """

    model_config = {"frozen": True}

    point: PointV1
    inputs: LoadInputs
    meta: PointMeta
    record: PointRecord
    warnings: tuple[str, ...] = ()


class CaptureStep(BaseModel):
    """Result of feeding data or ticking: live status and the capture if one happened."""

    model_config = {"frozen": True}

    status: StreamStatus
    captured: Captured | None = None


class CaptureController:
    """Drives one point at a time through a settle detector under a capture mode."""

    def __init__(
        self,
        stream: StreamConfig,
        config: CaptureConfig,
        resolver: RawRangeResolver,
        clock: Clock,
    ) -> None:
        """Wire the controller; prefer `create`, which validates mode consistency."""
        self._det = StreamingSettleDetector(stream)
        self._cfg = config
        self._resolve = resolver
        self._clock = clock
        self._started: float | None = None
        self._armed = False
        self._mass_kg = 0.0
        self._u_mass_kg = 0.0

    @classmethod
    def create(
        cls,
        stream: StreamConfig,
        config: CaptureConfig,
        resolver: RawRangeResolver,
        clock: Clock,
    ) -> Result[CaptureController, CaptureError]:
        """Build a controller; fixed_dwell capture and fixed_dwell detection must agree."""
        fixed_det = stream.mode is SettleMode.FIXED_DWELL
        if (config.mode is CaptureMode.FIXED_DWELL) != fixed_det:
            _log.error("capture mode %s vs detector mode %s", config.mode, stream.mode)
            return Err(CaptureError.ModeMismatch)
        _log.info("capture controller created mode=%s phase=%s", config.mode, config.phase)
        return Ok(cls(stream, config, resolver, clock))

    @property
    def detector(self) -> StreamingSettleDetector:
        """The underlying streaming detector (raw samples, finalized records)."""
        return self._det

    def start_point(
        self, t: float, mass_kg: float, u_mass_kg: float = 0.0
    ) -> Result[None, StreamError]:
        """Mark a load change at data time t with the total hanging mass; start the clock."""
        res = self._det.mark_load_change(t)
        if isinstance(res, Err):
            return res
        self._mass_kg = mass_kg
        self._u_mass_kg = u_mass_kg
        self._started = self._clock()
        self._armed = True
        _log.info("point started at t=%g (clock %g)", t, self._started)
        return Ok(None)

    def push(
        self, times: Sequence[float], lvdt: Sequence[float]
    ) -> Result[CaptureStep, SettleError | StreamError | CaptureError]:
        """Feed a raw block, then auto-capture if the mode and state call for it."""
        res = self._det.push(times, lvdt)
        if isinstance(res, Err):
            return Err(res.danger_err)
        return self._auto(res.danger_ok)

    def tick(self) -> Result[CaptureStep, StreamError | CaptureError]:
        """Re-check max wait without new data (timer tick); may auto-capture."""
        return self._auto(self._det.status)

    def accept(self) -> Result[Captured, StreamError | CaptureError]:
        """Human accept: capture now; before settled this records forced_early and warns."""
        if self._det.status.point_index is None:
            return Err(CaptureError.NoOpenPoint)
        settled = self._det.status.state is SettleState.SETTLED
        warnings: tuple[str, ...] = ()
        if not settled:
            warnings = ("accepted before settled: point recorded as forced_early",)
            _log.warning("%s", warnings[0])
        return self._capture(forced=not settled, warnings=warnings)

    def _auto(self, status: StreamStatus) -> Result[CaptureStep, StreamError | CaptureError]:
        """Apply the mode policy to the current status."""
        if status.point_index is None or self._cfg.mode is CaptureMode.CONFIRM:
            return Ok(CaptureStep(status=status))
        if not self._armed:
            # frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
            # no start_point since the last capture: the auto-opened point is the same load
            return Ok(CaptureStep(status=status))
        if status.state is SettleState.SETTLED:
            _log.info("auto-capture on settle (mode=%s)", self._cfg.mode)
            return self._step(status, forced=False, warnings=())
        if self._cfg.mode is CaptureMode.AUTO and self._waited() >= (self._cfg.max_wait_s or 0.0):
            msg = f"max wait {self._cfg.max_wait_s:g} s reached before settle: forced_early"
            _log.warning("%s", msg)
            return self._step(status, forced=True, warnings=(msg,))
        return Ok(CaptureStep(status=status))

    def _step(
        self, status: StreamStatus, *, forced: bool, warnings: tuple[str, ...]
    ) -> Result[CaptureStep, StreamError | CaptureError]:
        """Capture and wrap as a step."""
        cap = self._capture(forced=forced, warnings=warnings)
        if isinstance(cap, Err):
            return Err(cap.danger_err)
        return Ok(CaptureStep(status=status, captured=cap.danger_ok))

    def _waited(self) -> float:
        """Clock seconds since the point was started."""
        if self._started is None:
            self._started = self._clock()
        return self._clock() - self._started

    def _window_volts(self, start: float, end: float) -> tuple[float, float, float | None]:
        """Mean raw volts over [start, end], std error of the mean (0 if n<2) and sample std dev."""
        # frob:ticket 01M6WX3GGD2VSGEY1GT2X49DSV
        times, volts = self._det.raw
        ys = [y for t, y in zip(times, volts, strict=True) if start <= t <= end]
        n = len(ys)
        mean = math.fsum(ys) / n
        if n < 2:
            return mean, 0.0, None
        sd = math.sqrt(math.fsum((y - mean) ** 2 for y in ys) / (n - 1))
        return mean, sd / math.sqrt(n), sd

    def _capture(
        self, *, forced: bool, warnings: tuple[str, ...]
    ) -> Result[Captured, StreamError | CaptureError]:
        """Finalize the open point and build its POINT event with the raw seq range."""
        rec_res = self._det.force_early() if forced else self._det.close_point()
        if isinstance(rec_res, Err):
            return Err(rec_res.danger_err)
        rec = rec_res.danger_ok
        # the detector auto-opens the next point: restart the max-wait clock for it, but do not
        # auto-capture it again until start_point marks a new load (otherwise: same load forever)
        self._started = self._clock()
        self._armed = False
        if rec.window_start is None or rec.window_end is None:
            _log.error("point %d has no averaging window", rec.point_index)
            return Err(CaptureError.NoRawRange)
        window = self._resolve(rec.window_start, rec.window_end)
        if window is None:
            _log.error("no raw range for window [%g, %g]", rec.window_start, rec.window_end)
            return Err(CaptureError.NoRawRange)
        volts, u_volts, volts_sd = self._window_volts(rec.window_start, rec.window_end)
        inputs = LoadInputs(
            phase=self._cfg.phase,
            volts=volts,
            u_volts=u_volts,
            volts_sd=volts_sd,
            mass_kg=self._mass_kg,
            u_mass_kg=self._u_mass_kg,
        )
        meta = PointMeta(
            t_since_load_s=rec.time_since_load,
            drift_rate=rec.drift_rate.value if rec.drift_rate is not None else None,
            settled=rec.settled,
            forced_early=rec.forced_early,
        )
        point = build_point(inputs, window, meta)
        _log.info(
            "captured point %s settled=%s forced_early=%s seq=[%d,%d]",
            point.point_id,
            point.settled,
            point.forced_early,
            window.first_raw_seq,
            window.last_raw_seq,
        )
        return Ok(Captured(point=point, inputs=inputs, meta=meta, record=rec, warnings=warnings))


def set_window_edit(point_id: str, window: PointWindow) -> EditV1:
    """Build the append-only edit that moves a point's averaging window; replay recomputes."""
    args = window.model_dump(
        include={"first_raw_seq", "last_raw_seq", "first_sample", "last_sample"}
    )
    _log.info("window edit for point %s -> %s", point_id, args)
    return EditV1(target=point_id, op="set_window", args=args)
