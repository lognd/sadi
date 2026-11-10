"""AD3-driven LCTT test source: DwfBackend stimulus -> SADI ADC model -> pipeline-ready blocks."""

# frob:ticket 01M6Z32CP3XANNZ4ZRNGHQ8PEY
# frob:ticket 01M6Z53SMZTVJW9YGWRT1ZA5MF
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
    "BOARD_FULL_SCALE_V",
    "MAX_SAFE_V",
    "PACKET_LEN",
    "SAMPLES_PER_PACKET",
    "AdcModel",
    "Ad3Block",
    "Ad3Source",
    "Reading",
    "Segment",
    "encode_data_packet",
    "ramp_segments",
]

#: Hard ceiling on any AD3 output amplitude/offset used by the source (volts).
MAX_SAFE_V = 1.0
_N_CH = 4
#: Real SADI device-packet layout (crates/sadi-proto/src/codec/packet.rs).
PACKET_LEN = 612
SAMPLES_PER_PACKET = 50
_SYNC = 0x55
_TAIL = bytes([0xAA, 0x55, 0xAA, 0x55])
_TYPE_DATA = 5
_STATE_RUNNING = 3
_PAYLOAD_OFFSET = 8
_SAMPLE_LEN = 12  # int32 LE encoder + four u16 BE ADC words


#: Default SADI input range (AdcRange +-5.12 V); measured 6413 counts/V on firmware 1.003.
BOARD_FULL_SCALE_V = 5.12


class AdcModel(BaseModel):
    """Ideal SADI ADC input range: full scale in volts (bipolar 16 bit, real board +-5.12 V)."""

    model_config = ConfigDict(frozen=True)

    full_scale_v: float = Field(default=BOARD_FULL_SCALE_V, gt=0)

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


# frob:ticket 01M6Z3FR114SYB4SDYQVQPGZXY
def _encode_data_packet(msg_count: int, codes: NDArray[np.uint16]) -> bytes:
    """One 612-byte type-5 packet: `codes` is (50, 4) raw ADC words; encoder fields are zero."""
    f = bytearray(PACKET_LEN)
    f[0] = _SYNC
    f[1] = _TYPE_DATA
    f[2] = _STATE_RUNNING
    f[4:8] = msg_count.to_bytes(4, "little")
    for k in range(SAMPLES_PER_PACKET):
        o = _PAYLOAD_OFFSET + _SAMPLE_LEN * k
        f[o + 4 : o + _SAMPLE_LEN] = codes[k].astype(">u2").tobytes()
    f[PACKET_LEN - 4 :] = _TAIL
    return bytes(f)


# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
encode_data_packet = _encode_data_packet  # public name for non-AD3 sources (synthetic specimen)


@dataclass
class Ad3Block:
    """A pipeline `BlockLike` built from AD3-sourced volts with real SADI data-packet raw."""

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
    _seq: int = field(default=0, init=False)  # next data-packet msg_count

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

    # frob:ticket 01M6Z3FR114SYB4SDYQVQPGZXY
    def to_block(self, volts: NDArray[np.float64], packet_len: int = PACKET_LEN) -> Ad3Block:
        """Frame `volts` as real SADI type-5 data packets (sync, header, 50 samples, tail).

        A short final packet repeats its last sample, as the device always sends full packets;
        `msg_count` carries each sample's packet counter, continuing across blocks.
        """
        if packet_len != PACKET_LEN:
            raise ValueError(f"SADI data packets are {PACKET_LEN} bytes, not {packet_len}")
        n = len(volts)
        codes = np.array(
            [[self.adc.quantise(float(v)) for v in row] for row in volts], dtype=np.uint16
        ).reshape(n, _N_CH)
        n_pkts = -(-n // SAMPLES_PER_PACKET)
        if n_pkts * SAMPLES_PER_PACKET > n and n:
            fill = np.repeat(codes[-1:], n_pkts * SAMPLES_PER_PACKET - n, axis=0)
            codes = np.concatenate([codes, fill])
        start = self._seq
        frames = bytearray()
        for k in range(n_pkts):
            frames += _encode_data_packet(
                start + k, codes[k * SAMPLES_PER_PACKET : (k + 1) * SAMPLES_PER_PACKET]
            )
        self._seq += n_pkts
        _log.debug("ad3 to_block: %d samples -> %d packets from msg %d", n, n_pkts, start)
        return Ad3Block(
            volts=volts,
            raw=bytes(frames),
            msg_count=start + np.arange(n, dtype=np.int64) // SAMPLES_PER_PACKET,
            n_samples=n,
        )

    def stop(self) -> Result[None, DwfError]:
        """Stop generation on both routes (always call before closing the device)."""
        return stop_injection(self.be, self.dev, self.pins)
