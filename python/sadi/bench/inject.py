"""Drive any DwfBackend to inject LVDT-like and load signals into a SADI board and capture."""

# frob:ticket 01M6WSQ57BQ8EZYECPGPFQFWB7
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from typani import Err, Ok, Result

from sadi.bench.ad3.backend import DwfBackend, DwfError, OpenDevice, wait_acquired
from sadi.bench.ad3.consts import AcqMode, Channel, OutNode, WaveFunction
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = [
    "PinMap",
    "SADI_PINS",
    "SignalRoute",
    "capture",
    "counts_to_volts",
    "inject_dc",
    "inject_lvdt",
    "stop_injection",
    "volts_to_counts",
]


_ADC_BITS = 16
_ADC_MAX = (1 << _ADC_BITS) - 1
_CAPTURE_MARGIN_S = 2.0  # slack on top of samples/rate for arming and trigger latency


class SignalRoute(BaseModel):
    """One signal path: the AD3 analog out channel driving it and the scope channel observing it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    out_channel: int = Field(ge=0)
    scope_channel: int | None = Field(default=None, ge=0)
    sadi_channel: int | None = Field(default=None, ge=0)
    polarity: Literal["positive", "negative"] = "positive"


class PinMap(BaseModel):
    """Validated wiring of AD3 channels to SADI inputs; no two signals may share an out channel."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    lvdt: SignalRoute
    load: SignalRoute
    supply_scope_channel: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _distinct_outputs(self) -> PinMap:
        """Reject a map where lvdt and load drive the same analog out channel."""
        if self.lvdt.out_channel == self.load.out_channel:
            raise ValueError("lvdt and load must use different analog out channels")
        return self


# frob:ticket 01M6WT4Z643F7CJDFJT2GQ2J53
# Real bench wiring: AD3 W1+GND -> SADI ACH0 +/- (positive); W2+GND -> SADI ACH2 +/-
# (negative polarity); ACH1 floating; SADI GND/+3V3 -> AD3 scope ch 0 (supply monitor).
SADI_PINS = PinMap(
    lvdt=SignalRoute(out_channel=0, sadi_channel=0, polarity="positive"),
    load=SignalRoute(out_channel=1, sadi_channel=2, polarity="negative"),
    supply_scope_channel=0,
)


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
    # frob:ticket 01M6Z4EQZNMV31NM299XC9RPS4
    waited = wait_acquired(be, dev, timeout_s=samples / rate_hz + _CAPTURE_MARGIN_S)
    if not isinstance(waited, Ok):
        _log.error("capture wait failed ch=%d: %s", scope_channel, waited.unwrap_err().detail)
        return Err(waited.unwrap_err())
    data = be.in_data(dev, ch, samples)
    if isinstance(data, Ok):
        _log.info("captured ch=%d n=%d", scope_channel, len(data.unwrap()))
    return data
