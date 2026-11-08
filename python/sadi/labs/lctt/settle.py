"""LCTT settle detector: rolling LVDT drift slope, threshold and minimum dwell (pure, no I/O)."""

# frob:ticket 01M6W7R1KH0MVS56MX07Q9BX19

from __future__ import annotations

import math
from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, Field
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured

_log = get_logger(__name__)


class SettleError(ErrorSet):
    """Malformed detector input; the description says what to fix."""

    LengthMismatch = "times and lvdt must have equal length; pass one LVDT sample per timestamp"
    NonFinite = "Samples must be finite; drop or repair NaN/inf readings before detection"
    NonMonotonicTime = "Timestamps must be strictly increasing; check the acquisition clock"
    SlopeUnavailable = "Slope could not be built as Measured; check the window samples"


class NotSettledReason(StrEnum):
    """Why the detector has not (yet) declared the signal settled."""

    InsufficientData = "insufficient_data"
    SlopeAboveThreshold = "slope_above_threshold"
    SlopeUncertain = "slope_uncertain"
    DwellNotReached = "dwell_not_reached"


class SettleConfig(BaseModel):
    """Frozen detector parameters: window, slope threshold, minimum dwell and noise guard."""

    model_config = {"frozen": True}

    window_s: float = Field(gt=0, le=3600, description="Rolling slope window length, seconds")
    threshold: float = Field(gt=0, description="Max |drift rate| to count as settled, V/s")
    min_dwell_s: float = Field(ge=0, le=86400, description="Time the criterion must hold, s")
    min_points: int = Field(default=5, ge=3, le=100000, description="Fewest samples per window")
    unc_factor: float = Field(default=1.0, ge=0, le=10, description="k in |slope| + k*se <= thr")


class SettleResult(BaseModel):
    """Detector verdict: settle index/time, slope with uncertainty, or the reason it has not."""

    model_config = {"frozen": True}

    settled: bool
    settled_index: int | None = None
    settled_time: float | None = None
    confirmed_index: int | None = None
    slope: Measured | None = None
    window_points: int = 0
    reason: NotSettledReason | None = None


def _window_slope(t: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
    """OLS slope and its standard error over one window (se is inf if residuals undefined)."""
    n = len(t)
    tm = sum(t) / n
    ym = sum(y) / n
    sxx = sum((a - tm) ** 2 for a in t)
    sxy = sum((a - tm) * (b - ym) for a, b in zip(t, y, strict=True))
    slope = sxy / sxx
    sse = sum((b - ym - slope * (a - tm)) ** 2 for a, b in zip(t, y, strict=True))
    se = math.sqrt(sse / (n - 2) / sxx)
    return slope, se


def _validate(times: Sequence[float], lvdt: Sequence[float]) -> SettleError | None:
    """Return the first input problem found, or None."""
    if len(times) != len(lvdt):
        return SettleError.LengthMismatch
    if not all(math.isfinite(v) for v in times) or not all(math.isfinite(v) for v in lvdt):
        return SettleError.NonFinite
    if any(b <= a for a, b in zip(times, times[1:], strict=False)):
        return SettleError.NonMonotonicTime
    return None


class SettleScanner:
    """Sample-by-sample settle scan; incremental mode keeps O(1) amortized sliding-window sums."""

    def __init__(self, config: SettleConfig, *, incremental: bool = True) -> None:
        """Start an empty scan; incremental=False refits each window exactly (reference)."""
        self._cfg = config
        self._inc = incremental
        self._t: list[float] = []
        self._y: list[float] = []
        self._start = 0
        self._run_start: int | None = None
        self._run_slope: tuple[float, float, int] | None = None
        self._last_slope: tuple[float, float, int] | None = None
        self._reason = NotSettledReason.InsufficientData
        self._confirmed: int | None = None
        self._origin = (0.0, 0.0)
        self._sums = [0.0] * 6  # n, St, Sy, Stt, Sty, Syy about the origin
        self._since_rebuild = 0

    @property
    def n_fed(self) -> int:
        """Number of samples consumed so far."""
        return len(self._t)

    @property
    def last_time(self) -> float | None:
        """Timestamp of the latest sample, or None when empty."""
        return self._t[-1] if self._t else None

    @property
    def settled(self) -> bool:
        """True once the criterion has held for the minimum dwell."""
        return self._confirmed is not None

    def feed(self, times: Sequence[float], lvdt: Sequence[float]) -> None:
        """Consume validated samples; after settling they are only recorded."""
        for a, b in zip(times, lvdt, strict=True):
            self._t.append(a)
            self._y.append(b)
            if self._confirmed is None:
                self._step(len(self._t) - 1)

    def _rebuild(self) -> None:
        """Recompute the window sums exactly about the window's first sample."""
        s0 = self._start
        to, yo = self._t[s0], self._y[s0]
        self._origin = (to, yo)
        dt = [a - to for a in self._t[s0:]]
        dy = [b - yo for b in self._y[s0:]]
        self._sums = [
            float(len(dt)),
            sum(dt),
            sum(dy),
            sum(a * a for a in dt),
            sum(a * b for a, b in zip(dt, dy, strict=True)),
            sum(b * b for b in dy),
        ]
        self._since_rebuild = 0

    def _accumulate(self, i: int, sign: float) -> None:
        """Add (sign=1) or remove (sign=-1) sample i from the running sums."""
        dt, dy = self._t[i] - self._origin[0], self._y[i] - self._origin[1]
        for k, v in enumerate((1.0, dt, dy, dt * dt, dt * dy, dy * dy)):
            self._sums[k] += sign * v

    def _slope(self, i: int) -> tuple[float, float]:
        """OLS slope and standard error over the window ending at sample i."""
        lo = self._start
        if not self._inc:
            return _window_slope(self._t[lo : i + 1], self._y[lo : i + 1])
        n, st, sy, stt, sty, syy = self._sums
        sxx = stt - st * st / n
        if sxx <= 0.0:
            return _window_slope(self._t[lo : i + 1], self._y[lo : i + 1])
        sxy = sty - st * sy / n
        slope = sxy / sxx
        sse = max(0.0, syy - sy * sy / n - slope * sxy)
        return slope, math.sqrt(sse / (n - 2) / sxx)

    def _step(self, i: int) -> None:
        """Advance the scan by sample i, updating run state and the verdict."""
        cfg, times = self._cfg, self._t
        if self._inc:
            if i == 0:
                self._origin = (times[0], self._y[0])
            self._accumulate(i, 1.0)
        while times[i] - times[self._start] > cfg.window_s:
            if self._inc:
                self._accumulate(self._start, -1.0)
                self._since_rebuild += 1
            self._start += 1
        if self._inc and self._since_rebuild >= max(i - self._start + 1, 64):
            self._rebuild()
        npts = i - self._start + 1
        if npts < cfg.min_points or times[i] - times[0] < cfg.window_s:
            self._run_start = None
            self._reason = NotSettledReason.InsufficientData
            return
        slope, se = self._slope(i)
        self._last_slope = (slope, se, npts)
        if abs(slope) > cfg.threshold:
            self._run_start, self._reason = None, NotSettledReason.SlopeAboveThreshold
            return
        if abs(slope) + cfg.unc_factor * se > cfg.threshold:
            self._run_start, self._reason = None, NotSettledReason.SlopeUncertain
            return
        if self._run_start is None:
            self._run_start, self._run_slope = i, (slope, se, npts)
            _log.debug("settle criterion met at index %d (t=%g)", i, times[i])
        if self._run_slope is not None and times[i] - times[self._run_start] >= cfg.min_dwell_s:
            self._confirmed = i
            return
        self._reason = NotSettledReason.DwellNotReached

    def result(self) -> Result[SettleResult, SettleError]:
        """Verdict for the samples fed so far."""
        if self._confirmed is not None and self._run_start is not None and self._run_slope:
            return _build(self._run_start, self._confirmed, self._t, self._run_slope)
        if self._last_slope is None:
            return Ok(SettleResult(settled=False, reason=self._reason))
        slope_m = _measured(*self._last_slope)
        if isinstance(slope_m, Err):
            return Err(slope_m.danger_err)
        return Ok(
            SettleResult(
                settled=False,
                slope=slope_m.danger_ok,
                window_points=self._last_slope[2],
                reason=self._reason,
            )
        )


def detect_settle(
    times: Sequence[float], lvdt: Sequence[float], config: SettleConfig
) -> Result[SettleResult, SettleError]:
    """Suggest whether the LVDT has settled; never alters data, a human confirms the suggestion."""
    bad = _validate(times, lvdt)
    if bad is not None:
        _log.error("settle input rejected: %s", bad.name)
        return Err(bad)
    scan = SettleScanner(config, incremental=False)
    scan.feed(times, lvdt)
    res = scan.result()
    if isinstance(res, Ok) and not res.danger_ok.settled:
        _log.info("not settled after %d samples: %s", len(times), res.danger_ok.reason)
    return res


def _measured(slope: float, se: float, npts: int) -> Result[Measured, SettleError]:
    """Wrap a window slope as Measured in V/s with dof = n - 2."""
    m = Measured.create(slope, se, "V/s", dof=npts - 2)
    if isinstance(m, Err):
        _log.error("slope not representable: %s", m.danger_err.name)
        return Err(SettleError.SlopeUnavailable)
    return Ok(m.danger_ok)


def _build(
    first: int, confirmed: int, times: Sequence[float], sl: tuple[float, float, int]
) -> Result[SettleResult, SettleError]:
    """Assemble the settled verdict for a run starting at `first`, confirmed at `confirmed`."""
    m = _measured(*sl)
    if isinstance(m, Err):
        return Err(m.danger_err)
    _log.info("settled at index %d (t=%g), confirmed at %d", first, times[first], confirmed)
    return Ok(
        SettleResult(
            settled=True,
            settled_index=first,
            settled_time=times[first],
            confirmed_index=confirmed,
            slope=m.danger_ok,
            window_points=sl[2],
        )
    )
