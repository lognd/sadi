"""AD3-driven LCTT test source: DwfBackend stimulus -> SADI ADC model -> pipeline-ready blocks."""

# frob:ticket 01M6Z32CP3XANNZ4ZRNGHQ8PEY
from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field
from typani import Err, Ok, Result

from sadi.bench.ad3.backend import DwfBackend, DwfError, OpenDevice
from sadi.bench.inject import (
    SADI_PINS,
    PinMap,
    capture,
    counts_to_volts,
    inject_dc,
    inject_lvdt,
    stop_injection,
    volts_to_counts,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = [
    "MAX_SAFE_V",
    "AdcModel",
    "Ad3Block",
    "Ad3Source",
    "Reading",
    "Segment",
    "ramp_segments",
]

#: Hard ceiling on any AD3 output amplitude/offset used by the source (volts).
MAX_SAFE_V = 1.0
_SAMPLE_BYTES = 8  # four int16 channels per sample in the stand-in raw framing
_N_CH = 4


class AdcModel(BaseModel):
    """Ideal SADI ADC input range: full scale in volts (bipolar 16 bit, ADS8688 style)."""

    model_config = ConfigDict(frozen=True)

    full_scale_v: float = Field(default=1.25, gt=0)

    def quantise(self, volts: float) -> int:
        """ADC code for `volts`, clipped to the input range."""
        return volts_to_counts(volts, self.full_scale_v)

    def to_volts(self, code: int) -> float:
        """Volts the code represents."""
        return counts_to_volts(code, self.full_scale_v)


class Reading(BaseModel):
    """One ADC-quantised mean reading of both routes: lvdt (ACH0) and load (ACH2) volts."""

    model_config = ConfigDict(frozen=True)

    lvdt_v: float
    load_v: float
    lvdt_sd: float
    n: int


class Segment(BaseModel):
    """One constant stimulus dwell: route levels in volts held for `n` ADC samples."""

    model_config = ConfigDict(frozen=True)

    lvdt_v: float
    load_v: float = 0.0
    n: int = Field(gt=0)


def ramp_segments(
    lvdt: tuple[float, float], load: tuple[float, float], steps: int, n_each: int
) -> list[Segment]:
    """A linear staircase from the first to the last levels in `steps` equal dwells."""
    out: list[Segment] = []
    for k in range(steps):
        f = k / (steps - 1) if steps > 1 else 1.0
        out.append(
            Segment(
                lvdt_v=lvdt[0] + f * (lvdt[1] - lvdt[0]),
                load_v=load[0] + f * (load[1] - load[0]),
                n=n_each,
            )
        )
    return out


@dataclass
class Ad3Block:
    """A pipeline `BlockLike` built from AD3-sourced volts with count-packed stand-in raw."""

    volts: NDArray[np.float64]
    raw: bytes
    msg_count: NDArray[np.int64]
    n_samples: int
    dropped_bytes: int = 0
    gap_events: int = 0


@dataclass
class Ad3Source:
    """Produces LCTT input signals by driving an AD3 (fake or real) and reading it back.

    Route semantics follow `SADI_PINS`: W1 -> ACH0 (lvdt, positive), W2 -> ACH2 (load, negative
    polarity, so the ADC reports the negated applied voltage). Reads go through the `AdcModel`.
    """

    be: DwfBackend
    dev: OpenDevice
    adc: AdcModel = field(default_factory=AdcModel)
    pins: PinMap = SADI_PINS
    lvdt_scope: int = 0
    load_scope: int = 1
    rate_hz: float = 100_000.0
    max_chunk: int = 4096
    _seq: int = field(default=0, init=False)

    def _check(self, *levels: float) -> None:
        """Refuse levels above MAX_SAFE_V so a test can never over-drive the board."""
        for v in levels:
            if abs(v) > MAX_SAFE_V:
                raise ValueError(f"stimulus {v} V exceeds the {MAX_SAFE_V} V safety limit")

    def _sign(self) -> float:
        """-1 when the load route is wired to the negative ADC input."""
        return -1.0 if self.pins.load.polarity == "negative" else 1.0

    def _acquire(self, scope: int, n: int) -> Result[NDArray[np.float64], DwfError]:
        """Capture `n` samples from `scope` in buffer-sized chunks, quantised through the ADC."""
        out: list[float] = []
        while len(out) < n:
            take = min(self.max_chunk, n - len(out))
            got = capture(self.be, self.dev, scope, self.rate_hz, take)
            if not isinstance(got, Ok):
                return Err(got.danger_err)
            out.extend(self.adc.to_volts(self.adc.quantise(v)) for v in got.danger_ok)
        return Ok(np.array(out, dtype=np.float64))

    def dwell(self, seg: Segment) -> Result[NDArray[np.float64], DwfError]:
        """Hold `seg` on the AD3 and return its (n, 4) ADC volts (ch0 lvdt, ch2 load)."""
        self._check(seg.lvdt_v, seg.load_v)
        for res in (
            inject_lvdt(self.be, self.dev, self.pins, 0.0, 1000.0, offset_v=seg.lvdt_v),
            inject_dc(self.be, self.dev, self.pins, seg.load_v),
        ):
            if not isinstance(res, Ok):
                return Err(res.danger_err)
        lv = self._acquire(self.lvdt_scope, seg.n)
        if not isinstance(lv, Ok):
            return Err(lv.danger_err)
        ld = self._acquire(self.load_scope, seg.n)
        if not isinstance(ld, Ok):
            return Err(ld.danger_err)
        vol = np.zeros((seg.n, _N_CH))
        vol[:, 0] = lv.danger_ok
        vol[:, 2] = self._sign() * ld.danger_ok
        return Ok(vol)

    def stream(self, segments: Sequence[Segment]) -> Result[NDArray[np.float64], DwfError]:
        """Concatenate the dwells of `segments` into one (N, 4) volts stream."""
        parts: list[NDArray[np.float64]] = []
        for seg in segments:
            got = self.dwell(seg)
            if not isinstance(got, Ok):
                return got
            parts.append(got.danger_ok)
        _log.info("ad3 stream: %d segments, %d samples", len(parts), sum(len(p) for p in parts))
        return Ok(np.concatenate(parts))

    def read(self, lvdt_v: float, load_v: float = 0.0, n: int = 200) -> Result[Reading, DwfError]:
        """Mean ADC reading of a held level pair (what one captured point records)."""
        got = self.dwell(Segment(lvdt_v=lvdt_v, load_v=load_v, n=n))
        if not isinstance(got, Ok):
            return Err(got.danger_err)
        v = got.danger_ok
        return Ok(
            Reading(
                lvdt_v=float(v[:, 0].mean()),
                load_v=float(v[:, 2].mean()),
                lvdt_sd=float(v[:, 0].std(ddof=1)) if len(v) > 1 else 0.0,
                n=len(v),
            )
        )

    def sine_amplitude(
        self, amplitude_v: float, hz: float = 1000.0, cycles: int = 20
    ) -> Result[float, DwfError]:
        """Inject an LVDT sine and return its peak amplitude demodulated from the ADC samples."""
        self._check(amplitude_v)
        res = inject_lvdt(self.be, self.dev, self.pins, amplitude_v, hz)
        if not isinstance(res, Ok):
            return Err(res.danger_err)
        n = max(1, round(cycles * self.rate_hz / hz))
        got = self._acquire(self.lvdt_scope, min(n, self.max_chunk))
        if not isinstance(got, Ok):
            return Err(got.danger_err)
        x = got.danger_ok
        return Ok(math.sqrt(2.0 * float(np.mean(x * x))))

    def to_block(self, volts: NDArray[np.float64], packet_len: int = 612) -> Ad3Block:
        """Pack `volts` as int16 ADC codes, zero-padded to whole `packet_len` packets."""
        codes = np.array([[self.adc.quantise(float(v)) for v in row] for row in volts], dtype=">u2")
        raw = codes.tobytes()
        pad = (-len(raw)) % packet_len
        start = self._seq
        self._seq += len(volts)
        return Ad3Block(
            volts=volts,
            raw=raw + bytes(pad),
            msg_count=np.arange(start, start + len(volts), dtype=np.int64),
            n_samples=len(volts),
        )

    def stop(self) -> Result[None, DwfError]:
        """Stop generation on both routes (always call before closing the device)."""
        return stop_injection(self.be, self.dev, self.pins)
