"""Device-agnostic DWF backend contract: errors, typestate handles, DwfBackend Protocol."""

# frob:ticket 01M6WSPW5XB6P5V3PR5SHEH6FP
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

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

__all__ = [
    "ClosedDevice",
    "DeviceInfo",
    "DwfBackend",
    "DwfCode",
    "DwfError",
    "OpenDevice",
    "hint_for",
    "library_steps",
    "numbered",
]


class DwfCode(ErrorSet):
    """Failure codes for the DWF binding."""

    LIBRARY_MISSING = "library missing"
    DEVICE_NOT_FOUND = "device not found"
    CALL_FAILED = "call failed"
    HANDLE_CLOSED = "handle closed"
    BAD_RESPONSE = "bad response"


_INSTALL_ANY = "Install Digilent WaveForms (includes the DWF runtime) from the Digilent website."
_SET_ENV = "If the library is in a non-standard place, set SADI_DWF_LIB to its full path."
_USBIPD = (
    "WSL only: in an admin Windows shell run `usbipd list`, then `usbipd bind --busid <id>`, "
    "then `usbipd attach --wsl --busid <id>` to pass the USB device into WSL."
)


def library_steps(platform: str, wsl: bool = False) -> tuple[str, ...]:
    """Return the ordered fix steps for a missing libdwf on `platform` (a sys.platform value)."""
    if platform.startswith("win"):
        return (
            "Install Digilent WaveForms for Windows; it provides dwf.dll in System32.",
            _SET_ENV,
            "Re-run the command.",
        )
    if platform.startswith("darwin"):
        return (
            "Install Digilent WaveForms from the macOS .dmg; it provides "
            "/Library/Frameworks/dwf.framework.",
            _SET_ENV,
            "Re-run the command.",
        )
    steps = [
        _INSTALL_ANY,
        "Install the Digilent Adept runtime so the USB device is accessible.",
        "Confirm libdwf.so exists (for example under /usr/lib/digilent/waveforms).",
    ]
    if wsl:
        steps.append(_USBIPD)
    steps += [_SET_ENV, "Re-run the command."]
    return tuple(steps)


_DEVICE_STEPS = (
    "Plug the Analog Discovery 3 in by USB and wait for its LED to turn on.",
    "Close WaveForms and any other program that holds the device.",
    "WSL users: run `usbipd attach --wsl --busid <id>` again after replugging.",
    "Re-run the command.",
)
_CALL_STEPS = (
    "Read the detail message from the DWF library shown with this error.",
    "Check the arguments (channel index, range, frequency) against the device limits.",
    "Replug the device and retry; report it if it repeats.",
)
_CLOSED_STEPS = (
    "Open the device again with the backend's open() and use the new handle.",
    "A closed handle cannot be reused; keep only the handle open() returned last.",
)
_BAD_STEPS = (
    "Update the Digilent WaveForms runtime to the latest version.",
    "Report the detail message if it repeats.",
)
_STEPS: dict[ErrorSet, tuple[str, ...]] = {
    DwfCode.LIBRARY_MISSING: library_steps("linux"),
    DwfCode.DEVICE_NOT_FOUND: _DEVICE_STEPS,
    DwfCode.CALL_FAILED: _CALL_STEPS,
    DwfCode.HANDLE_CLOSED: _CLOSED_STEPS,
    DwfCode.BAD_RESPONSE: _BAD_STEPS,
}


def numbered(steps: tuple[str, ...]) -> str:
    """Render steps as a numbered list, one per line."""
    return "\n".join(f"{n}. {s}" for n, s in enumerate(steps, 1))


def hint_for(code: ErrorSet) -> str:
    """Return the default numbered, step-by-step fix hint for a DWF error code."""
    return numbered(_STEPS[code])


class DwfError(BaseModel):
    """Frozen DWF failure: a code, the library's last-error text, and its native erc if known."""

    model_config = ConfigDict(frozen=True)

    code: DwfCode
    detail: str = ""
    erc: int | None = None
    steps: tuple[str, ...] | None = None

    @property
    def hint(self) -> str:
        """Numbered fix steps for this error (OS-specific when `steps` was supplied)."""
        return numbered(self.steps) if self.steps is not None else hint_for(self.code)


class DeviceInfo(BaseModel):
    """One enumerated device: index, name, serial number and family id (None when unknown)."""

    model_config = ConfigDict(frozen=True)

    index: int
    name: str
    serial: str
    device_id: DeviceId | None = None


class ClosedDevice:
    """A device that is not open; it has no operations, only the index it was opened from."""

    __slots__ = ("index",)

    def __init__(self, index: int) -> None:
        """Record the enumeration index this closed device came from."""
        self.index = index

    def __repr__(self) -> str:
        """Return a short debug form."""
        return f"ClosedDevice(index={self.index})"


class OpenDevice:
    """Move-only open device handle; close() consumes it, after which every call returns Err."""

    __slots__ = ("_hdwf", "_live", "index")

    def __init__(self, hdwf: int, index: int) -> None:
        """Wrap a native handle; only backends construct these."""
        self._hdwf = hdwf
        self._live = True
        self.index = index

    @property
    def is_open(self) -> bool:
        """True until the handle has been consumed by close()."""
        return self._live

    def native(self) -> Result[int, DwfError]:
        """Return the native handle, or Err(HANDLE_CLOSED) once consumed."""
        if not self._live:
            _log.warning("use of consumed device handle index=%d", self.index)
            return Err(
                DwfError(code=DwfCode.HANDLE_CLOSED, detail=f"device {self.index} is closed")
            )
        return Ok(self._hdwf)

    def consume(self) -> Result[ClosedDevice, DwfError]:
        """Mark the handle consumed and return its ClosedDevice; Err if already consumed."""
        if not self._live:
            _log.warning("double close of device index=%d", self.index)
            return Err(
                DwfError(code=DwfCode.HANDLE_CLOSED, detail=f"device {self.index} is closed")
            )
        self._live = False
        _log.info("device index=%d consumed", self.index)
        return Ok(ClosedDevice(self.index))

    def __repr__(self) -> str:
        """Return a short debug form."""
        return f"OpenDevice(index={self.index}, open={self._live})"


class DwfBackend(Protocol):
    """Everything SADI's bench code needs from a DWF implementation (real ctypes or a fake)."""

    def version(self) -> Result[str, DwfError]:
        """Return the DWF library version string."""
        ...

    def set_on_close(self, mode: int) -> Result[None, DwfError]:
        """Set what devices do on close: 0 keep running, 1 stop, 2 shut down."""
        ...

    def enumerate_devices(
        self, flt: EnumFilter = EnumFilter.ALL
    ) -> Result[list[DeviceInfo], DwfError]:
        """List attached devices matching `flt`."""
        ...

    def open(self, index: int) -> Result[OpenDevice, DwfError]:
        """Open the device at `index` (-1 = first available); Err(DEVICE_NOT_FOUND) if none."""
        ...

    def close(self, dev: OpenDevice) -> Result[ClosedDevice, DwfError]:
        """Close `dev`, consuming the handle."""
        ...

    def auto_configure(self, dev: OpenDevice, enable: bool) -> Result[None, DwfError]:
        """Enable or disable automatic reconfiguration on every setter call."""
        ...

    # -- analog out --------------------------------------------------------------------
    def out_node_enable(
        self, dev: OpenDevice, ch: Channel, node: OutNode, enable: bool
    ) -> Result[None, DwfError]:
        """Enable or disable an analog out node."""
        ...

    def out_node_function(
        self, dev: OpenDevice, ch: Channel, node: OutNode, func: WaveFunction
    ) -> Result[None, DwfError]:
        """Select the waveform of an analog out node."""
        ...

    def out_node_frequency(
        self, dev: OpenDevice, ch: Channel, node: OutNode, hz: float
    ) -> Result[None, DwfError]:
        """Set an analog out node frequency in hertz."""
        ...

    def out_node_amplitude(
        self, dev: OpenDevice, ch: Channel, node: OutNode, volts: float
    ) -> Result[None, DwfError]:
        """Set an analog out node amplitude in volts."""
        ...

    def out_node_offset(
        self, dev: OpenDevice, ch: Channel, node: OutNode, volts: float
    ) -> Result[None, DwfError]:
        """Set an analog out node offset in volts."""
        ...

    def out_configure(self, dev: OpenDevice, ch: Channel, start: bool) -> Result[None, DwfError]:
        """Apply analog out settings for `ch`, optionally starting generation."""
        ...

    # -- analog in (scope) -------------------------------------------------------------
    def in_reset(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Reset the analog in instrument to defaults."""
        ...

    def in_channel_enable(
        self, dev: OpenDevice, ch: Channel, enable: bool
    ) -> Result[None, DwfError]:
        """Enable or disable a scope channel."""
        ...

    def in_channel_range(
        self, dev: OpenDevice, ch: Channel, volts: float
    ) -> Result[None, DwfError]:
        """Set a scope channel full-scale range in volts."""
        ...

    def in_channel_offset(
        self, dev: OpenDevice, ch: Channel, volts: float
    ) -> Result[None, DwfError]:
        """Set a scope channel offset in volts."""
        ...

    def in_frequency(self, dev: OpenDevice, hz: float) -> Result[None, DwfError]:
        """Set the scope sample rate in hertz."""
        ...

    def in_buffer_size(self, dev: OpenDevice, samples: int) -> Result[None, DwfError]:
        """Set the scope buffer length in samples."""
        ...

    def in_acquisition_mode(self, dev: OpenDevice, mode: AcqMode) -> Result[None, DwfError]:
        """Select the scope acquisition mode."""
        ...

    def in_configure(
        self, dev: OpenDevice, reconfigure: bool, start: bool
    ) -> Result[None, DwfError]:
        """Apply scope settings and optionally start acquisition."""
        ...

    def in_status(self, dev: OpenDevice, read_data: bool) -> Result[AcqState, DwfError]:
        """Poll the scope state, optionally latching data for in_data()."""
        ...

    def in_data(self, dev: OpenDevice, ch: Channel, count: int) -> Result[list[float], DwfError]:
        """Return `count` volt samples of `ch` from the last status(read_data=True)."""
        ...

    # -- analog IO (supplies) ----------------------------------------------------------
    def io_enable(self, dev: OpenDevice, enable: bool) -> Result[None, DwfError]:
        """Set the analog IO master enable (power supplies)."""
        ...

    def io_node_set(
        self, dev: OpenDevice, ch: Channel, node: IoNode, value: float
    ) -> Result[None, DwfError]:
        """Set an analog IO node value (for example a supply voltage)."""
        ...

    def io_configure(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Apply analog IO settings."""
        ...

    def io_status(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Latch analog IO readings for io_node_status()."""
        ...

    def io_node_status(self, dev: OpenDevice, ch: Channel, node: IoNode) -> Result[float, DwfError]:
        """Return the latched reading of an analog IO node."""
        ...

    # -- digital IO --------------------------------------------------------------------
    def dio_output_enable(self, dev: OpenDevice, mask: int) -> Result[None, DwfError]:
        """Set which digital pins are outputs (bit mask)."""
        ...

    def dio_output(self, dev: OpenDevice, mask: int) -> Result[None, DwfError]:
        """Set digital output pin states (bit mask)."""
        ...

    def dio_configure(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Apply digital IO settings."""
        ...

    def dio_status(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Latch digital input state for dio_input()."""
        ...

    def dio_input(self, dev: OpenDevice) -> Result[int, DwfError]:
        """Return the latched digital input bit mask."""
        ...
