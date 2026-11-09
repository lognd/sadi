"""High-level AD3 wrapper: typestate (Ad3Closed -> Ad3Session) with Result everywhere."""

# frob:ticket 01M6Z335HGJVJD2MG8NZ37V6TP
from __future__ import annotations

import math
from types import TracebackType
from typing import Never

from typani import Err, Ok, Result, propagate

from sadi.bench.ad3.backend import (
    ClosedDevice,
    DeviceInfo,
    DwfBackend,
    DwfCode,
    DwfError,
    OpenDevice,
    wait_acquired,
)
from sadi.bench.ad3.consts import (
    FIRST_DEVICE,
    AcqMode,
    Channel,
    IoNode,
    OutNode,
    WaveFunction,
)
from sadi.bench.ad3.dll import load_backend
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = ["Ad3Closed", "Ad3Session", "open_ad3"]

# AD3 analog IO layout: channel 0 is the positive supply, channel 1 the negative supply;
# node 0 is that supply's enable, node 1 its voltage.
SUPPLY_ENABLE_NODE = IoNode(0)
SUPPLY_VOLTAGE_NODE = IoNode(1)
_SUPPLY_CHANNELS = {"positive": Channel(0), "negative": Channel(1)}


def _bad(detail: str) -> Err[Never, DwfError]:
    """Build the Err for an argument the wrapper rejects before touching the device."""
    _log.warning("ad3 wrapper rejected argument: %s", detail)
    return Err(DwfError(code=DwfCode.BAD_ARGUMENT, detail=detail))


class Ad3Closed:
    """A configured-but-closed AD3: the only state from which open() is possible."""

    def __init__(self, backend: DwfBackend, index: int = FIRST_DEVICE) -> None:
        """Hold the backend and the enumeration index to open (-1 = first available)."""
        self.backend = backend
        self.index = index

    @classmethod
    def from_library(cls, index: int = FIRST_DEVICE) -> Result[Ad3Closed, DwfError]:
        """Load the real DWF library; Err(LIBRARY_MISSING) carries per-OS fix steps."""
        return load_backend().map(lambda be: cls(be, index))

    def enumerate(self) -> Result[list[DeviceInfo], DwfError]:
        """List attached devices without opening any."""
        return self.backend.enumerate_devices()

    def open(self) -> Result[Ad3Session, DwfError]:
        """Open the device and move to the open state; the Err keeps this object reusable."""
        res = self.backend.open(self.index)
        if isinstance(res, Err):
            _log.error("ad3 open index=%d failed: %s", self.index, res.unwrap_err().code.value)
            return Err(res.unwrap_err())
        _log.info("ad3 session opened index=%d", self.index)
        return Ok(Ad3Session(self.backend, res.unwrap()))

    def __repr__(self) -> str:
        """Return a short debug form."""
        return f"Ad3Closed(index={self.index})"


class Ad3Session:
    """An open AD3 context manager; after close() every call is Err(HANDLE_CLOSED)."""

    def __init__(self, backend: DwfBackend, dev: OpenDevice) -> None:
        """Wrap a freshly opened native device; only Ad3Closed.open() constructs these."""
        self._be = backend
        self._dev = dev

    @property
    def is_open(self) -> bool:
        """True until close() has run."""
        return self._dev.is_open

    def __enter__(self) -> Ad3Session:
        """Enter the context; the session is already open."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Close on leaving the context; a failed close is logged, never raised over the body."""
        if self._dev.is_open:
            res = self.close()
            if isinstance(res, Err):
                _log.error("ad3 close on context exit failed: %s", res.unwrap_err().code.value)

    def close(self) -> Result[Ad3Closed, DwfError]:
        """Close the device and return the Ad3Closed that can reopen it (Err if already shut)."""
        res: Result[ClosedDevice, DwfError] = self._be.close(self._dev)
        if isinstance(res, Err):
            return Err(res.unwrap_err())
        _log.info("ad3 session closed index=%d", self._dev.index)
        return Ok(Ad3Closed(self._be, res.unwrap().index))

    def version(self) -> Result[str, DwfError]:
        """Return the DWF library version string."""
        return self._be.version()

    # -- supplies ----------------------------------------------------------------------
    @propagate
    def set_supply(self, side: str, volts: float) -> Result[None, DwfError]:
        """Set the 'positive' or 'negative' supply voltage and enable it."""
        ch = _SUPPLY_CHANNELS.get(side)
        if ch is None:
            return _bad(f"supply side {side!r} must be one of {sorted(_SUPPLY_CHANNELS)}")
        self._be.io_node_set(self._dev, ch, SUPPLY_VOLTAGE_NODE, volts).unwrap()
        self._be.io_node_set(self._dev, ch, SUPPLY_ENABLE_NODE, 1.0).unwrap()
        self._be.io_enable(self._dev, True).unwrap()
        self._be.io_configure(self._dev).unwrap()
        _log.info("ad3 %s supply set to %.3f V", side, volts)
        return Ok(None)

    @propagate
    def supplies_off(self) -> Result[None, DwfError]:
        """Disable the master supply enable (both rails)."""
        self._be.io_enable(self._dev, False).unwrap()
        self._be.io_configure(self._dev).unwrap()
        _log.info("ad3 supplies off")
        return Ok(None)

    # -- wavegen -----------------------------------------------------------------------
    @propagate
    def wave(
        self,
        ch: int,
        func: WaveFunction,
        hz: float,
        amplitude_v: float,
        offset_v: float = 0.0,
    ) -> Result[None, DwfError]:
        """Start a carrier waveform on analog out channel `ch`."""
        c = Channel(ch)
        node = OutNode.CARRIER
        self._be.out_node_enable(self._dev, c, node, True).unwrap()
        self._be.out_node_function(self._dev, c, node, func).unwrap()
        self._be.out_node_frequency(self._dev, c, node, hz).unwrap()
        self._be.out_node_amplitude(self._dev, c, node, amplitude_v).unwrap()
        self._be.out_node_offset(self._dev, c, node, offset_v).unwrap()
        self._be.out_configure(self._dev, c, True).unwrap()
        _log.info("ad3 wave ch=%d %s %.3f Hz %.3f V", ch, func.name, hz, amplitude_v)
        return Ok(None)

    @propagate
    def stop_wave(self, ch: int) -> Result[None, DwfError]:
        """Stop generation on analog out channel `ch`."""
        c = Channel(ch)
        self._be.out_node_enable(self._dev, c, OutNode.CARRIER, False).unwrap()
        self._be.out_configure(self._dev, c, False).unwrap()
        _log.info("ad3 wave stopped ch=%d", ch)
        return Ok(None)

    # -- scope -------------------------------------------------------------------------
    @propagate
    def capture(
        self,
        ch: int,
        hz: float,
        samples: int,
        range_v: float = 5.0,
        offset_v: float = 0.0,
        timeout_s: float = 10.0,
    ) -> Result[list[float], DwfError]:
        """Acquire `samples` volts from scope channel `ch` at `hz`; bounded by `timeout_s`."""
        if isinstance(samples, bool) or samples <= 0:
            return _bad(f"samples={samples!r} must be a positive int")
        if not (math.isfinite(hz) and hz > 0):
            return _bad(f"hz={hz!r} must be finite and > 0")
        c = Channel(ch)
        be, dev = self._be, self._dev
        be.in_reset(dev).unwrap()
        be.in_channel_enable(dev, c, True).unwrap()
        be.in_channel_range(dev, c, range_v).unwrap()
        be.in_channel_offset(dev, c, offset_v).unwrap()
        be.in_frequency(dev, hz).unwrap()
        be.in_buffer_size(dev, samples).unwrap()
        be.in_acquisition_mode(dev, AcqMode.SINGLE).unwrap()
        be.in_configure(dev, True, True).unwrap()
        wait_acquired(be, dev, timeout_s).unwrap()
        data = be.in_data(dev, c, samples).unwrap()
        _log.info("ad3 captured %d samples ch=%d at %.1f Hz", len(data), ch, hz)
        return Ok(data)

    # -- digital -----------------------------------------------------------------------
    @propagate
    def dio_write(self, output_mask: int, value: int) -> Result[None, DwfError]:
        """Drive the pins in `output_mask` to the matching bits of `value`."""
        self._be.dio_output_enable(self._dev, output_mask).unwrap()
        self._be.dio_output(self._dev, value & output_mask).unwrap()
        self._be.dio_configure(self._dev).unwrap()
        return Ok(None)

    @propagate
    def dio_read(self) -> Result[int, DwfError]:
        """Latch and return the digital input bit mask."""
        self._be.dio_status(self._dev).unwrap()
        return self._be.dio_input(self._dev)

    def __repr__(self) -> str:
        """Return a short debug form."""
        return f"Ad3Session(index={self._dev.index}, open={self._dev.is_open})"


def open_ad3(
    backend: DwfBackend | None = None, index: int = FIRST_DEVICE
) -> Result[Ad3Session, DwfError]:
    """Open the AD3 in one step (real library unless `backend` is given), ready for `with`."""
    if backend is None:
        loaded = load_backend()
        if isinstance(loaded, Err):
            return Err(loaded.unwrap_err())
        backend = loaded.unwrap()
    return Ad3Closed(backend, index).open()
