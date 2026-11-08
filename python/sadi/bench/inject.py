"""Drive any DwfBackend to inject LVDT-like and load signals into a SADI board and capture."""

# frob:ticket 01M6WSQ57BQ8EZYECPGPFQFWB7
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typani import Err, Ok, Result

from sadi.bench.ad3.backend import DwfBackend, DwfError, OpenDevice
from sadi.bench.ad3.consts import AcqMode, AcqState, Channel, OutNode, WaveFunction
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = [
    "PinMap",
    "SignalRoute",
    "capture",
    "counts_to_volts",
    "inject_dc",
    "inject_lvdt",
    "stop_injection",
    "volts_to_counts",
]


# frob:todo 2GQ2J53 real-board pin mapping is unknown; PinMap is supplied by the hardware session.
_ADC_BITS = 16
_ADC_MAX = (1 << _ADC_BITS) - 1


class SignalRoute(BaseModel):
    """One signal path: the AD3 analog out channel driving it and the scope channel observing it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    out_channel: int = Field(ge=0)
    scope_channel: int | None = Field(default=None, ge=0)


class PinMap(BaseModel):
    """Validated wiring of AD3 channels to SADI inputs; no two signals may share an out channel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lvdt: SignalRoute
    load: SignalRoute

    @model_validator(mode="after")
    def _distinct_outputs(self) -> PinMap:
        """Reject a map where lvdt and load drive the same analog out channel."""
        if self.lvdt.out_channel == self.load.out_channel:
            raise ValueError("lvdt and load must use different analog out channels")
        return self


def volts_to_counts(volts: float, full_scale: float) -> int:
    """Ideal bipolar 16-bit ADC (ADS8688 style) code for `volts` with +-`full_scale`, clipped."""
    code = round((volts / full_scale + 1.0) / 2.0 * _ADC_MAX)
    return max(0, min(_ADC_MAX, code))


def counts_to_volts(code: int, full_scale: float) -> float:
    """Inverse of volts_to_counts: the ideal volts a bipolar 16-bit code represents."""
    return (code / _ADC_MAX * 2.0 - 1.0) * full_scale


def _drive(
    be: DwfBackend,
    dev: OpenDevice,
    ch: Channel,
    func: WaveFunction,
    hz: float,
    amplitude: float,
    offset: float,
) -> Result[None, DwfError]:
    """Configure and start one carrier on out channel `ch`, stopping at the first error."""
    steps = (
        lambda: be.out_node_enable(dev, ch, OutNode.CARRIER, True),
        lambda: be.out_node_function(dev, ch, OutNode.CARRIER, func),
        lambda: be.out_node_frequency(dev, ch, OutNode.CARRIER, hz),
        lambda: be.out_node_amplitude(dev, ch, OutNode.CARRIER, amplitude),
        lambda: be.out_node_offset(dev, ch, OutNode.CARRIER, offset),
        lambda: be.out_configure(dev, ch, True),
    )
    for step in steps:
        res = step()
        if not isinstance(res, Ok):
            _log.error("inject drive failed ch=%d: %s", ch, res.unwrap_err().detail)
            return res
    _log.info("inject ch=%d %s hz=%g amp=%g off=%g", ch, func.name, hz, amplitude, offset)
    return Ok(None)


def inject_lvdt(
    be: DwfBackend,
    dev: OpenDevice,
    pins: PinMap,
    amplitude_v: float,
    freq_hz: float,
    offset_v: float = 0.0,
) -> Result[None, DwfError]:
    """Inject an LVDT-like sine (amplitude tracks displacement) on the lvdt route."""
    return _drive(
        be, dev, Channel(pins.lvdt.out_channel), WaveFunction.SINE, freq_hz, amplitude_v, offset_v
    )


def inject_dc(
    be: DwfBackend, dev: OpenDevice, pins: PinMap, volts: float
) -> Result[None, DwfError]:
    """Inject a DC level (a load-channel reading) on the load route."""
    return _drive(be, dev, Channel(pins.load.out_channel), WaveFunction.DC, 1.0, 0.0, volts)


def stop_injection(be: DwfBackend, dev: OpenDevice, pins: PinMap) -> Result[None, DwfError]:
    """Stop generation on both routes."""
    for route in (pins.lvdt, pins.load):
        res = be.out_configure(dev, Channel(route.out_channel), False)
        if not isinstance(res, Ok):
            return res
    _log.info("injection stopped")
    return Ok(None)


def capture(
    be: DwfBackend,
    dev: OpenDevice,
    scope_channel: int,
    rate_hz: float,
    samples: int,
    range_v: float = 10.0,
) -> Result[list[float], DwfError]:
    """Acquire `samples` volts from one scope channel in single-shot mode."""
    ch = Channel(scope_channel)
    steps = (
        lambda: be.in_reset(dev),
        lambda: be.in_channel_enable(dev, ch, True),
        lambda: be.in_channel_range(dev, ch, range_v),
        lambda: be.in_frequency(dev, rate_hz),
        lambda: be.in_buffer_size(dev, samples),
        lambda: be.in_acquisition_mode(dev, AcqMode.SINGLE),
        lambda: be.in_configure(dev, True, True),
    )
    for step in steps:
        res = step()
        if not isinstance(res, Ok):
            _log.error("capture setup failed ch=%d: %s", scope_channel, res.unwrap_err().detail)
            return Err(res.unwrap_err())
    state = be.in_status(dev, True)
    if not isinstance(state, Ok):
        return Err(state.unwrap_err())
    if state.unwrap() != AcqState.DONE:
        _log.warning("capture not done state=%s", state.unwrap().name)
    data = be.in_data(dev, ch, samples)
    if isinstance(data, Ok):
        _log.info("captured ch=%d n=%d", scope_channel, len(data.unwrap()))
    return data
