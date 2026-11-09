"""Deterministic in-memory DwfBackend: out waveforms sampled by scope channels, no hardware."""

# frob:ticket 01M6WSQ57BQ8EZYECPGPFQFWB7
# frob:ticket 01M6Z3FR6FP6TTP9BW4MHJSE85
from __future__ import annotations

import math
import random

from pydantic import BaseModel, ConfigDict, Field
from typani import Err, Ok, Result

from sadi.bench.ad3.backend import ClosedDevice, DeviceInfo, DwfCode, DwfError, OpenDevice
from sadi.bench.ad3.consts import (
    AcqMode,
    AcqState,
    Channel,
    DeviceId,
    EnumFilter,
    IoNode,
    OutNode,
    WaveFunction,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = ["FakeConfig", "FakeDwf", "ScopeCal"]

_FAKE_NATIVE_HANDLE = 1
_SINGLE_MODES = (AcqMode.SINGLE, AcqMode.SINGLE1)
_STREAM_MODES = (AcqMode.SCAN_SHIFT, AcqMode.SCAN_SCREEN, AcqMode.RECORD)


class ScopeCal(BaseModel):
    """Per-scope-channel calibration: reading = gain * (signal + noise) + offset_v, clipped."""

    model_config = ConfigDict(frozen=True)

    gain: float = 1.0
    offset_v: float = 0.0
    noise_v: float = Field(default=0.0, ge=0.0)


class FakeConfig(BaseModel):
    """Fake device configuration; `wiring` maps scope channel -> analog out channel (loopback)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    seed: int = 0
    serial: str = "SN:FAKE000001"
    wiring: dict[int, int] = Field(default_factory=lambda: {0: 0, 1: 1})
    cal: dict[int, ScopeCal] = Field(default_factory=dict)
    max_buffer: int = Field(default=8192, gt=0)


class _OutState(BaseModel):
    """Mutable settings of one analog out channel (carrier node only)."""

    enabled: bool = False
    func: WaveFunction = WaveFunction.DC
    hz: float = 1000.0
    amplitude: float = 1.0
    offset: float = 0.0
    running: bool = False


class _ScopeState(BaseModel):
    """Mutable settings of one scope channel."""

    enabled: bool = False
    range_v: float = 5.0
    offset: float = 0.0


def _bad(detail: str) -> DwfError:
    """Build (and log) the CALL_FAILED error for a rejected argument."""
    _log.warning("fake dwf rejected call: %s", detail)
    return DwfError(code=DwfCode.CALL_FAILED, detail=detail)


def waveform(func: WaveFunction, phase: float) -> float | None:
    """Return the unit waveform in [-1, 1] at `phase` cycles, or None if unsupported."""
    frac = phase - math.floor(phase)
    if func == WaveFunction.DC:
        return 0.0
    if func == WaveFunction.SINE:
        return math.sin(2.0 * math.pi * phase)
    if func == WaveFunction.SQUARE:
        return 1.0 if frac < 0.5 else -1.0
    if func == WaveFunction.TRIANGLE:
        return 4.0 * abs(frac - 0.5) - 1.0
    if func == WaveFunction.RAMP_UP:
        return 2.0 * frac - 1.0
    if func == WaveFunction.RAMP_DOWN:
        return 1.0 - 2.0 * frac
    return None


class FakeDwf:
    """Hardware-free DwfBackend: scope channels sample the (wired) analog out channels."""

    def __init__(self, config: FakeConfig | None = None) -> None:
        """Create a fake with one device; `config` sets wiring, calibration and noise seed."""
        self.config = config or FakeConfig()
        self._rng = random.Random(self.config.seed)
        self._open = False
        self._out: dict[int, _OutState] = {}
        self._scope: dict[int, _ScopeState] = {}
        self._rate = 1.0e6
        self._size = 512
        self._armed = False
        self._mode = AcqMode.SINGLE
        self._cursor = 0
        self._latched: dict[int, list[float]] = {}
        self._io: dict[tuple[int, int], float] = {}
        self._dio_dir = 0
        self._dio_out = 0
        self.custom: dict[int, list[float]] = {}

    # -- helpers -----------------------------------------------------------------------
    def set_custom(self, ch: Channel, samples: list[float]) -> None:
        """Make `ch` replay one period of `samples` (volts) at its set frequency."""
        self.custom[int(ch)] = list(samples)
        _log.info("fake custom waveform ch=%d n=%d", ch, len(samples))

    def _live(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Err(HANDLE_CLOSED) when `dev` was consumed."""
        h = dev.native()
        if not isinstance(h, Ok):
            return Err(h.unwrap_err())
        return Ok(None)

    def _out_value(self, ch: int, t: float) -> float:
        """Voltage of out channel `ch` at time `t` seconds since start."""
        st = self._out.get(ch)
        if st is None or not st.enabled or not st.running:
            return 0.0
        phase = st.hz * t
        if ch in self.custom and self.custom[ch]:
            buf = self.custom[ch]
            frac = phase - math.floor(phase)
            return buf[int(frac * len(buf)) % len(buf)]
        unit = waveform(st.func, phase)
        return st.offset + st.amplitude * (unit if unit is not None else 0.0)

    def _sample(self, ch: int, n: int, start: int = 0) -> list[float]:
        """Generate `n` calibrated, clipped, noisy readings of scope `ch` from sample `start`."""
        cal = self.config.cal.get(ch, ScopeCal())
        sc = self._scope[ch]
        src = self.config.wiring.get(ch)
        half = sc.range_v / 2.0
        out: list[float] = []
        for k in range(n):
            sig = self._out_value(src, (start + k) / self._rate) if src is not None else 0.0
            noise = self._rng.gauss(0.0, cal.noise_v) if cal.noise_v > 0.0 else 0.0
            v = cal.gain * (sig + noise) + cal.offset_v - sc.offset
            out.append(max(-half, min(half, v)))
        return out

    # -- session -----------------------------------------------------------------------
    def version(self) -> Result[str, DwfError]:
        """Return a fixed fake version string."""
        return Ok("fake-3.0")

    def set_on_close(self, mode: int) -> Result[None, DwfError]:
        """Accept 0..2, reject anything else."""
        if mode not in (0, 1, 2):
            return Err(_bad(f"on-close mode {mode} out of range"))
        return Ok(None)

    def enumerate_devices(
        self, flt: EnumFilter = EnumFilter.ALL
    ) -> Result[list[DeviceInfo], DwfError]:
        """List the single fake AD3."""
        info = DeviceInfo(
            index=0,
            name="Fake Analog Discovery 3",
            serial=self.config.serial,
            device_id=DeviceId.DISCOVERY3,
        )
        return Ok([info])

    def open(self, index: int) -> Result[OpenDevice, DwfError]:
        """Open the fake device (index 0 or -1); Err(DEVICE_NOT_FOUND) otherwise or if open."""
        if index not in (-1, 0) or self._open:
            _log.warning("fake open failed index=%d already_open=%s", index, self._open)
            return Err(DwfError(code=DwfCode.DEVICE_NOT_FOUND, detail=f"no device at {index}"))
        self._open = True
        self._armed = False
        self._out.clear()
        self._scope.clear()
        _log.info("fake device opened")
        return Ok(OpenDevice(_FAKE_NATIVE_HANDLE, 0))

    def close(self, dev: OpenDevice) -> Result[ClosedDevice, DwfError]:
        """Close the fake device, consuming the handle."""
        res = dev.consume()
        if isinstance(res, Ok):
            self._open = False
        return res

    def auto_configure(self, dev: OpenDevice, enable: bool) -> Result[None, DwfError]:
        """Accept and ignore (the fake always applies settings immediately)."""
        return self._live(dev)

    # -- analog out --------------------------------------------------------------------
    def _out_st(self, dev: OpenDevice, ch: Channel) -> Result[_OutState, DwfError]:
        """Fetch (creating) the state of out channel `ch` after checking the handle."""
        live = self._live(dev)
        if not isinstance(live, Ok):
            return Err(live.unwrap_err())
        if ch < 0 or ch > 1:
            return Err(_bad(f"analog out channel {ch} out of range"))
        return Ok(self._out.setdefault(int(ch), _OutState()))

    def out_node_enable(
        self, dev: OpenDevice, ch: Channel, node: OutNode, enable: bool
    ) -> Result[None, DwfError]:
        """Enable or disable the carrier of out channel `ch`."""
        st = self._out_st(dev, ch)
        if not isinstance(st, Ok):
            return Err(st.unwrap_err())
        st.unwrap().enabled = enable
        return Ok(None)

    def out_node_function(
        self, dev: OpenDevice, ch: Channel, node: OutNode, func: WaveFunction
    ) -> Result[None, DwfError]:
        """Select the waveform; Err for functions the fake cannot model."""
        st = self._out_st(dev, ch)
        if not isinstance(st, Ok):
            return Err(st.unwrap_err())
        if waveform(func, 0.0) is None:
            return Err(_bad(f"waveform {func.name} not supported by FakeDwf"))
        st.unwrap().func = func
        return Ok(None)

    def out_node_frequency(
        self, dev: OpenDevice, ch: Channel, node: OutNode, hz: float
    ) -> Result[None, DwfError]:
        """Set the out frequency; must be positive."""
        st = self._out_st(dev, ch)
        if not isinstance(st, Ok):
            return Err(st.unwrap_err())
        if hz <= 0.0:
            return Err(_bad(f"frequency {hz} must be positive"))
        st.unwrap().hz = hz
        return Ok(None)

    def out_node_amplitude(
        self, dev: OpenDevice, ch: Channel, node: OutNode, volts: float
    ) -> Result[None, DwfError]:
        """Set the out amplitude in volts."""
        st = self._out_st(dev, ch)
        if not isinstance(st, Ok):
            return Err(st.unwrap_err())
        st.unwrap().amplitude = volts
        return Ok(None)

    def out_node_offset(
        self, dev: OpenDevice, ch: Channel, node: OutNode, volts: float
    ) -> Result[None, DwfError]:
        """Set the out offset in volts."""
        st = self._out_st(dev, ch)
        if not isinstance(st, Ok):
            return Err(st.unwrap_err())
        st.unwrap().offset = volts
        return Ok(None)

    def out_configure(self, dev: OpenDevice, ch: Channel, start: bool) -> Result[None, DwfError]:
        """Start or stop generation on `ch`."""
        st = self._out_st(dev, ch)
        if not isinstance(st, Ok):
            return Err(st.unwrap_err())
        st.unwrap().running = start
        return Ok(None)

    # -- analog in ---------------------------------------------------------------------
    def _scope_st(self, dev: OpenDevice, ch: Channel) -> Result[_ScopeState, DwfError]:
        """Fetch (creating) the state of scope channel `ch` after checking the handle."""
        live = self._live(dev)
        if not isinstance(live, Ok):
            return Err(live.unwrap_err())
        if ch < 0 or ch > 1:
            return Err(_bad(f"scope channel {ch} out of range"))
        return Ok(self._scope.setdefault(int(ch), _ScopeState()))

    def in_reset(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Reset scope settings and drop any acquisition."""
        live = self._live(dev)
        if isinstance(live, Ok):
            self._scope.clear()
            self._latched.clear()
            self._armed = False
        return live

    def in_channel_enable(
        self, dev: OpenDevice, ch: Channel, enable: bool
    ) -> Result[None, DwfError]:
        """Enable or disable scope channel `ch`."""
        st = self._scope_st(dev, ch)
        if not isinstance(st, Ok):
            return Err(st.unwrap_err())
        st.unwrap().enabled = enable
        return Ok(None)

    def in_channel_range(
        self, dev: OpenDevice, ch: Channel, volts: float
    ) -> Result[None, DwfError]:
        """Set the full-scale span; samples clip at half of it around the offset."""
        st = self._scope_st(dev, ch)
        if not isinstance(st, Ok):
            return Err(st.unwrap_err())
        if volts <= 0.0:
            return Err(_bad(f"range {volts} must be positive"))
        st.unwrap().range_v = volts
        return Ok(None)

    def in_channel_offset(
        self, dev: OpenDevice, ch: Channel, volts: float
    ) -> Result[None, DwfError]:
        """Set the scope channel offset in volts."""
        st = self._scope_st(dev, ch)
        if not isinstance(st, Ok):
            return Err(st.unwrap_err())
        st.unwrap().offset = volts
        return Ok(None)

    def in_frequency(self, dev: OpenDevice, hz: float) -> Result[None, DwfError]:
        """Set the sample rate; must be positive."""
        live = self._live(dev)
        if not isinstance(live, Ok):
            return live
        if hz <= 0.0:
            return Err(_bad(f"sample rate {hz} must be positive"))
        self._rate = hz
        return Ok(None)

    def in_buffer_size(self, dev: OpenDevice, samples: int) -> Result[None, DwfError]:
        """Set the buffer length within 1..max_buffer."""
        live = self._live(dev)
        if not isinstance(live, Ok):
            return live
        if not 1 <= samples <= self.config.max_buffer:
            return Err(_bad(f"buffer size {samples} outside 1..{self.config.max_buffer}"))
        self._size = samples
        return Ok(None)

    def in_acquisition_mode(self, dev: OpenDevice, mode: AcqMode) -> Result[None, DwfError]:
        """Accept SINGLE/SINGLE1 and the continuous SCAN_SHIFT/SCAN_SCREEN/RECORD modes."""
        live = self._live(dev)
        if not isinstance(live, Ok):
            return live
        if mode not in _SINGLE_MODES and mode not in _STREAM_MODES:
            return Err(_bad(f"acquisition mode {mode.name} not supported by FakeDwf"))
        self._mode = mode
        _log.info("fake acquisition mode %s", mode.name)
        return Ok(None)

    def in_configure(
        self, dev: OpenDevice, reconfigure: bool, start: bool
    ) -> Result[None, DwfError]:
        """Arm (start) an acquisition; it completes instantly on the next status poll."""
        live = self._live(dev)
        if isinstance(live, Ok):
            self._armed = start
            self._cursor = 0
        return live

    def in_status(self, dev: OpenDevice, read_data: bool) -> Result[AcqState, DwfError]:
        """Return DONE (single) or TRIGGERED (streaming) once armed, latching data if asked.

        In streaming modes each read_data poll latches the next contiguous block, so the
        waveform phase continues across polls and the acquisition never completes.
        """
        live = self._live(dev)
        if not isinstance(live, Ok):
            return Err(live.unwrap_err())
        if not self._armed:
            return Ok(AcqState.READY)
        streaming = self._mode in _STREAM_MODES
        if read_data:
            self._latched = {
                ch: self._sample(ch, self._size, self._cursor)
                for ch, s in self._scope.items()
                if s.enabled
            }
            if streaming:
                self._cursor += self._size
        return Ok(AcqState.TRIGGERED if streaming else AcqState.DONE)

    def in_data(self, dev: OpenDevice, ch: Channel, count: int) -> Result[list[float], DwfError]:
        """Return up to `count` latched samples of `ch`; Err if none were latched."""
        live = self._live(dev)
        if not isinstance(live, Ok):
            return Err(live.unwrap_err())
        buf = self._latched.get(int(ch))
        if buf is None:
            return Err(_bad(f"no latched data for scope channel {ch}"))
        return Ok(buf[:count])

    # -- analog IO ---------------------------------------------------------------------
    def io_enable(self, dev: OpenDevice, enable: bool) -> Result[None, DwfError]:
        """Accept the supply master enable."""
        return self._live(dev)

    def io_node_set(
        self, dev: OpenDevice, ch: Channel, node: IoNode, value: float
    ) -> Result[None, DwfError]:
        """Store a supply node value (readback returns it exactly)."""
        live = self._live(dev)
        if isinstance(live, Ok):
            self._io[(int(ch), int(node))] = value
        return live

    def io_configure(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Accept analog IO configuration."""
        return self._live(dev)

    def io_status(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Accept an analog IO latch."""
        return self._live(dev)

    def io_node_status(self, dev: OpenDevice, ch: Channel, node: IoNode) -> Result[float, DwfError]:
        """Return the stored node value (0.0 if never set)."""
        live = self._live(dev)
        if not isinstance(live, Ok):
            return Err(live.unwrap_err())
        return Ok(self._io.get((int(ch), int(node)), 0.0))

    # -- digital IO --------------------------------------------------------------------
    def dio_output_enable(self, dev: OpenDevice, mask: int) -> Result[None, DwfError]:
        """Store which digital pins are outputs."""
        live = self._live(dev)
        if isinstance(live, Ok):
            self._dio_dir = mask
        return live

    def dio_output(self, dev: OpenDevice, mask: int) -> Result[None, DwfError]:
        """Store digital output states."""
        live = self._live(dev)
        if isinstance(live, Ok):
            self._dio_out = mask
        return live

    def dio_configure(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Accept digital IO configuration."""
        return self._live(dev)

    def dio_status(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Accept a digital IO latch."""
        return self._live(dev)

    def dio_input(self, dev: OpenDevice) -> Result[int, DwfError]:
        """Return output-driven pins as read back (digital loopback on driven pins)."""
        live = self._live(dev)
        if not isinstance(live, Ok):
            return Err(live.unwrap_err())
        return Ok(self._dio_out & self._dio_dir)
