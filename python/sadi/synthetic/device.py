"""SyntheticDevice: a DeviceService stand-in streaming real-format packets from a simulated wire."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

import threading
import time
from typing import Final

import numpy as np
from typani import Ok, Result

from sadi.bench.lctt_source import (
    BOARD_FULL_SCALE_V,
    PACKET_LEN,
    SAMPLES_PER_PACKET,
    Ad3Block,
    encode_data_packet,
)
from sadi.core.device import DeviceFault, DeviceStatus
from sadi.core.errors import DeviceError
from sadi.logging_setup import get_logger
from sadi.synthetic.scenario import HANGER_KG, N_PER_V, SHORT_L0_M, G
from sadi.synthetic.specimen import CopperSpec

_log = get_logger(__name__)

__all__ = ["BLOCK_SAMPLES", "DEVICE_RATE_HZ", "SyntheticDevice"]

DEVICE_RATE_HZ: Final = 50_000
_PACKETS_PER_BLOCK: Final = 25
BLOCK_SAMPLES: Final = _PACKETS_PER_BLOCK * SAMPLES_PER_PACKET
_ADC_MAX: Final = 65535
_FAULT_EVERY: Final = 20  # blocks between injected faults
#: Hanging-mass step (kg) each "load applied" press adds on the synthetic wire.
SYNTH_LOAD_STEP_KG: Final = 0.01


def _to_codes(volts: np.ndarray, full_scale: float) -> np.ndarray:
    """Ideal bipolar 16-bit ADC codes for `volts`, clipped to the input range."""
    codes = np.rint((volts / full_scale + 1.0) / 2.0 * _ADC_MAX)
    return np.clip(codes, 0, _ADC_MAX).astype(np.uint16)


class SyntheticDevice:
    """A seeded, deterministic copper-wire source with the `DeviceService` surface the app uses.

    Never real hardware: `is_simulator` stays False (so no sim-only code path fires) and
    `is_synthetic` is True. LVDT is on ACH0 and the load cell on ACH2.
    """

    is_synthetic: Final = True
    is_simulator: Final = False

    def __init__(
        self,
        seed: int = 0,
        spec: CopperSpec | None = None,
        faults: frozenset[str] = frozenset(),
        realtime: bool = True,
        l0_m: float = SHORT_L0_M,
        cal_slope_m_per_v: float = 0.005,
        tare_v: float = 0.0,
    ) -> None:
        """Hold the wire model and the deterministic noise stream for `seed`."""
        self._spec = spec or CopperSpec()
        self._rng = np.random.default_rng(seed)
        self._faults = faults
        self._realtime = realtime
        self._scale = l0_m / cal_slope_m_per_v
        self._tare_v = tare_v
        self._sd = 0.004
        self._lock = threading.Lock()
        self._open = False
        self._streaming = False
        self._msg = 0
        self._blocks = 0
        self._cum_kg = 0.0
        self._smax = 0.0
        self._t_hold = 0.0
        self._ref = self._spec.strain(HANGER_KG * G / self._spec.area_m2, 0.0)

    @property
    def status(self) -> DeviceStatus:
        """simulated while open, error otherwise (the UI shows the synthetic strip either way)."""
        return DeviceStatus.SIMULATED if self._open else DeviceStatus.ERROR

    @property
    def fault(self) -> DeviceFault | None:
        """Never faults; the synthetic stream cannot fail."""
        return None

    @property
    def mass_kg(self) -> float:
        """Total mass currently hung (hanger excluded)."""
        return self._cum_kg

    def open(self) -> Result[None, DeviceError]:
        """Mark the source open; always Ok."""
        self._open = True
        _log.warning("synthetic device open: streaming SIMULATED copper wire")
        return Ok(None)

    def sim_add_weight(self, kg: float) -> Result[float, DeviceError]:
        """Hang `kg` more mass now and restart the hold clock (Ok is the new total)."""
        with self._lock:
            self._cum_kg = round(self._cum_kg + kg, 6)
            self._t_hold = 0.0
            total = self._cum_kg
        _log.info("synthetic load applied: %.3f kg hung", total)
        return Ok(total)

    def advance_load(self) -> Result[float, DeviceError]:
        """Hang the next standard step of mass (what a 'load applied' press does here)."""
        return self.sim_add_weight(SYNTH_LOAD_STEP_KG)

    def start_streaming(self, adc_mode: object = None) -> Result[None, DeviceError]:
        """Begin emitting blocks; resets the hold clock."""
        with self._lock:
            self._streaming = True
            self._t_hold = 0.0
        _log.info("synthetic streaming started")
        return Ok(None)

    def next_block(self, timeout: float | None = 1.0) -> Result[Ad3Block | None, DeviceFault]:
        """Next 25-packet block (1250 samples), or Ok(None) when not streaming."""
        if not self._streaming:
            time.sleep(min(timeout or 0.0, 0.01))
            return Ok(None)
        if self._realtime:
            time.sleep(BLOCK_SAMPLES / DEVICE_RATE_HZ)
        return Ok(self._make_block())

    def stop_streaming(self) -> Result[list[Ad3Block], DeviceError]:
        """Stop emitting; nothing is queued, so the trailing list is empty."""
        self._streaming = False
        _log.info("synthetic streaming stopped after %d blocks", self._blocks)
        return Ok([])

    def close(self) -> None:
        """Close the source; safe in any state."""
        self._streaming = False
        self._open = False
        _log.info("synthetic device closed")

    def _make_block(self) -> Ad3Block:
        """Build one block of framed packets from the current load and hold time."""
        with self._lock:
            n = BLOCK_SAMPLES
            stress = self._spec.cap((self._cum_kg + HANGER_KG) * G / self._spec.area_m2)
            self._smax = max(self._smax, stress)
            t0 = self._t_hold
            t = t0 + np.arange(n) / DEVICE_RATE_HZ
            creep = np.array(
                [self._spec.creep_strain(stress, float(x)) for x in t[::SAMPLES_PER_PACKET]]
            )
            creep = np.repeat(creep, SAMPLES_PER_PACKET)
            base = self._spec.strain(stress, self._smax, 0.0)
            lvdt = self._tare_v + (base + creep - self._ref) * self._scale
            volts = np.zeros((n, 4))
            volts[:, 0] = lvdt + self._rng.normal(0.0, self._sd, n)
            volts[:, 2] = stress * self._spec.area_m2 / N_PER_V + self._rng.normal(0.0, 0.002, n)
            self._t_hold = t0 + n / DEVICE_RATE_HZ
            self._blocks += 1
            dropped = 0
            skip = 0
            if self._blocks % _FAULT_EVERY == 0:
                if "spike" in self._faults:
                    volts[n // 2, 0] += 1.0
                if "saturation" in self._faults:
                    volts[n // 2 : n // 2 + 20, 0] = BOARD_FULL_SCALE_V
                if "dropped_frames" in self._faults:
                    dropped, skip = PACKET_LEN, 1
            codes = _to_codes(volts, BOARD_FULL_SCALE_V)
            start = self._msg + skip
            self._msg = start + _PACKETS_PER_BLOCK
        raw = b"".join(
            encode_data_packet(
                start + k, codes[k * SAMPLES_PER_PACKET : (k + 1) * SAMPLES_PER_PACKET]
            )
            for k in range(_PACKETS_PER_BLOCK)
        )
        back = (codes.astype(np.float64) / _ADC_MAX * 2.0 - 1.0) * BOARD_FULL_SCALE_V
        return Ad3Block(
            volts=back,
            raw=raw,
            msg_count=start + np.arange(n, dtype=np.int64) // SAMPLES_PER_PACKET,
            n_samples=n,
            dropped_bytes=dropped,
            gap_events=1 if dropped else 0,
        )
