"""LCTT streaming settle layer: LVDT blocks and load-change markers to per-point records."""

# frob:ticket 01M6W8Z1JAJTQR9KHPMH1A73VD

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator
from typani import Err, ErrorSet, Ok, Result

from sadi.labs.lctt.settle import SettleConfig, SettleError, SettleScanner, _window_slope
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured

_log = get_logger(__name__)


class StreamError(ErrorSet):
    """Misuse of the streaming detector; the description says what to fix."""

    BadMarker = "Load-change time must be finite and not earlier than the previous marker"
    NoOpenPoint = "No open point; mark a load change before closing or forcing a point"


class SettleState(StrEnum):
    """Streaming verdict for the open point."""

    LOADING = "loading"
    CREEPING = "creeping"
    SETTLED = "settled"


class SettleMode(StrEnum):
    """Settle criterion: drift-slope detector, or a fixed dwell after the load change."""

    DRIFT = "drift"
    FIXED_DWELL = "fixed_dwell"


class StreamConfig(BaseModel):
    """Frozen streaming parameters: detector config, mode and the fixed dwell if used."""

    model_config = {"frozen": True}

    settle: SettleConfig
    mode: SettleMode = SettleMode.DRIFT
    fixed_dwell_s: float | None = Field(
        default=None, gt=0, le=86400, description="Dwell after load change, s (fixed mode)"
    )

    @model_validator(mode="after")
    def _need_dwell(self) -> StreamConfig:
        """Fixed-dwell mode requires fixed_dwell_s."""
        if self.mode is SettleMode.FIXED_DWELL and self.fixed_dwell_s is None:
            raise ValueError("fixed_dwell_s is required when mode is fixed_dwell")
        return self


class StreamStatus(BaseModel):
    """Live status: state, drift rate (V/s) and seconds since the load change."""

    model_config = {"frozen": True}

    state: SettleState
    point_index: int | None = None
    time_since_load: float | None = None
    drift_rate: Measured | None = None


class PointRecord(BaseModel):
    """Per-point result: window, time since load, drift rate, settled and forced-early flags."""

    model_config = {"frozen": True}

    point_index: int
    load_change_time: float
    window_start: float | None = None
    window_end: float | None = None
    time_since_load: float
    drift_rate: Measured | None = None
    settled: bool
    forced_early: bool
    mode: SettleMode
    n_samples: int


class _Point:
    """Mutable working state of the open point."""

    def __init__(self, index: int, t_load: float) -> None:
        self.index = index
        self.t_load = t_load
        self.t: list[float] = []
        self.y: list[float] = []
        self.latched: StreamStatus | None = None
        self.latched_n = 0
        self.checked_n = 0
        self.fed_n = 0
        self.capped = False
        self.scanner: SettleScanner | None = None
        self.status = StreamStatus(state=SettleState.LOADING, point_index=index)


class StreamingSettleDetector:
    """Feeds raw LVDT blocks through the settle detector; raw is kept in every state."""

    def __init__(self, config: StreamConfig) -> None:
        """Create a detector with no open point; samples before a marker are raw only."""
        self._cfg = config
        self._raw_t: list[float] = []
        self._raw_y: list[float] = []
        self._points: list[PointRecord] = []
        self._open: _Point | None = None
        self._last_marker = -math.inf
        self._count = 0

    @property
    def raw(self) -> tuple[tuple[float, ...], tuple[float, ...]]:
        """All samples received (times, lvdt), regardless of state."""
        return tuple(self._raw_t), tuple(self._raw_y)

    @property
    def records(self) -> tuple[PointRecord, ...]:
        """Finalized per-point records, in order."""
        return tuple(self._points)

    @property
    def status(self) -> StreamStatus:
        """Current status; LOADING with no point when no load change was marked."""
        if self._open is None:
            return StreamStatus(state=SettleState.LOADING)
        return self._open.status

    def mark_load_change(self, t: float) -> Result[None, StreamError]:
        """Close any open point as unsettled and start a new one at time t."""
        if not math.isfinite(t) or t < self._last_marker:
            _log.error("bad load-change marker t=%r", t)
            return Err(StreamError.BadMarker)
        if self._open is not None:
            _log.info("load change at t=%g closes unsettled point %d", t, self._open.index)
            self._finalize(forced=False)
        self._last_marker = t
        self._open = _Point(self._count, t)
        self._count += 1
        _log.info("load change marker t=%g, point %d opened", t, self._open.index)
        return Ok(None)

    def push(
        self, times: Sequence[float], lvdt: Sequence[float]
    ) -> Result[StreamStatus, SettleError | StreamError]:
        """Record a raw block, then update and return the open point's status."""
        if len(times) != len(lvdt):
            return Err(SettleError.LengthMismatch)
        if not all(math.isfinite(v) for v in (*times, *lvdt)):
            return Err(SettleError.NonFinite)
        prev = self._raw_t[-1] if self._raw_t else -math.inf
        if any(b <= a for a, b in zip((prev, *times), times, strict=False)):
            _log.error("block rejected: non-increasing timestamps")
            return Err(SettleError.NonMonotonicTime)
        self._raw_t.extend(times)
        self._raw_y.extend(lvdt)
        pt = self._open
        if pt is None:
            return Ok(self.status)
        for a, b in zip(times, lvdt, strict=True):
            if a >= pt.t_load:
                pt.t.append(a)
                pt.y.append(b)
        if pt.latched is not None and len(pt.t) > pt.checked_n:
            pt.checked_n = len(pt.t)
            self._recheck_latched(pt)
        if pt.latched is None and len(pt.t) > pt.checked_n:
            pt.checked_n = len(pt.t)
            res = self._evaluate(pt)
            if isinstance(res, Err):
                return Err(res.danger_err)
            pt.status = res.danger_ok
        return Ok(pt.status)

    def close_point(self) -> Result[PointRecord, StreamError]:
        """Finalize the open point (settled if latched, else unsettled) and open the next."""
        if self._open is None:
            return Err(StreamError.NoOpenPoint)
        rec = self._finalize(forced=False)
        self._reopen()
        return Ok(rec)

    def force_early(self) -> Result[PointRecord, StreamError]:
        """Finalize the open point as forced early unless settled, and open the next."""
        if self._open is None:
            return Err(StreamError.NoOpenPoint)
        rec = self._finalize(forced=self._open.latched is None)
        self._reopen()
        return Ok(rec)

    def _reopen(self) -> None:
        """Open a fresh point at the latest sample so the next capture needs no manual mark."""
        t = max(self._raw_t[-1] if self._raw_t else -math.inf, self._last_marker)
        if not math.isfinite(t):
            return
        self._last_marker = t
        self._open = _Point(self._count, t)
        self._count += 1
        _log.info("auto-opened point %d at t=%g after capture", self._open.index, t)

    def _recheck_latched(self, pt: _Point) -> None:
        """Drop a drift-mode settle verdict when the trailing window drifts above threshold."""
        if self._cfg.mode is SettleMode.FIXED_DWELL:
            return
        cfg = self._cfg.settle
        lo = len(pt.t) - 1
        while lo > 0 and pt.t[-1] - pt.t[lo - 1] <= cfg.window_s:
            lo -= 1
        if len(pt.t) - lo < max(cfg.min_points, 3):
            return
        slope, _ = _window_slope(pt.t[lo:], pt.y[lo:])
        if abs(slope) <= cfg.threshold:
            return
        _log.info("point %d unsettled again: trailing drift %.3g", pt.index, slope)
        pt.latched, pt.latched_n = None, 0
        pt.capped = False
        pt.scanner = None
        pt.fed_n = lo
        pt.status = StreamStatus(
            state=SettleState.CREEPING, point_index=pt.index, time_since_load=pt.t[-1] - pt.t_load
        )

    def _evaluate(self, pt: _Point) -> Result[StreamStatus, SettleError]:
        """Run the detector on the point's samples and map to a status; latch on settle."""
        cfg = self._cfg
        fixed = cfg.mode is SettleMode.FIXED_DWELL
        if pt.scanner is None:
            pt.scanner = SettleScanner(cfg.settle)
        end = len(pt.t)
        if fixed and not pt.capped:
            assert cfg.fixed_dwell_s is not None
            for i in range(pt.fed_n, end):
                if pt.t[i] - pt.t_load >= cfg.fixed_dwell_s:
                    end, pt.capped = i + 1, True
                    break
        elif pt.capped:
            end = pt.fed_n
        pt.scanner.feed(pt.t[pt.fed_n : end], pt.y[pt.fed_n : end])
        pt.fed_n = end
        res = pt.scanner.result()
        if isinstance(res, Err):
            return Err(res.danger_err)
        r = res.danger_ok
        last = pt.scanner.last_time
        assert last is not None
        since = last - pt.t_load
        if fixed:
            done = since >= (cfg.fixed_dwell_s or 0.0)
            drift = r.slope
        else:
            done = r.settled
            drift = r.slope
            if done and r.settled_time is not None:
                since = r.settled_time - pt.t_load
        if done:
            st = StreamStatus(
                state=SettleState.SETTLED,
                point_index=pt.index,
                time_since_load=since,
                drift_rate=drift,
            )
            pt.latched, pt.latched_n = st, end
            _log.info("point %d settled (%s) at %.3g s since load", pt.index, cfg.mode, since)
            return Ok(st)
        state = SettleState.CREEPING if r.slope is not None else SettleState.LOADING
        return Ok(
            StreamStatus(state=state, point_index=pt.index, time_since_load=since, drift_rate=drift)
        )

    def _finalize(self, *, forced: bool) -> PointRecord:
        """Turn the open point into a PointRecord and clear it."""
        pt = self._open
        assert pt is not None
        st = pt.latched or pt.status
        n = pt.latched_n if pt.latched is not None else len(pt.t)
        end = pt.t[n - 1] if n else None
        win = self._cfg.settle.window_s
        start = next((a for a in pt.t[:n] if end is not None and a >= end - win), None)
        rec = PointRecord(
            point_index=pt.index,
            load_change_time=pt.t_load,
            window_start=start,
            window_end=end,
            time_since_load=st.time_since_load if st.time_since_load is not None else 0.0,
            drift_rate=st.drift_rate,
            settled=pt.latched is not None,
            forced_early=forced,
            mode=self._cfg.mode,
            n_samples=len(pt.t),
        )
        self._points.append(rec)
        self._open = None
        _log.info(
            "point %d finalized settled=%s forced_early=%s", rec.point_index, rec.settled, forced
        )
        return rec
