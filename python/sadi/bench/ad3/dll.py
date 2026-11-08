"""The single ctypes edge: lazy libdwf discovery and CtypesBackend, the real DwfBackend."""

# frob:ticket 01M6WSPW5XB6P5V3PR5SHEH6FP
from __future__ import annotations

import ctypes
import ctypes.util
import os
import sys
from collections.abc import Callable, Mapping
from typing import Any

from typani import Err, Ok, Result

from sadi.bench.ad3.backend import (
    ClosedDevice,
    DeviceInfo,
    DwfCode,
    DwfError,
    OpenDevice,
    library_steps,
)
from sadi.bench.ad3.consts import (
    ENV_LIB_PATH,
    ERROR_MSG_LEN,
    FIRST_DEVICE,
    HDWF_NONE,
    NAME_LEN,
    VERSION_LEN,
    AcqMode,
    AcqState,
    Channel,
    DeviceId,
    DwfParam,
    EnumFilter,
    IoNode,
    OutNode,
    WaveFunction,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = ["CtypesBackend", "candidate_names", "is_wsl", "load_backend", "load_library"]

Loader = Callable[[str], Any]
_DEFAULT_LOADER: Loader = ctypes.cdll.LoadLibrary


def is_wsl(proc_version: str) -> bool:
    """True when the text of /proc/version identifies a WSL kernel (contains 'microsoft')."""
    return "microsoft" in proc_version.lower()


def _read_proc_version() -> str:
    """Return /proc/version text, or '' when unreadable (non-Linux)."""
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def candidate_names(
    platform: str,
    env: Mapping[str, str] | None = None,
    finder: Callable[[str], str | None] | None = None,
) -> list[str]:
    """Return library names/paths to try in order: SADI_DWF_LIB, then per-OS defaults (pure)."""
    names: list[str] = []
    override = (env or {}).get(ENV_LIB_PATH)
    if override is not None and override != "":
        names.append(override)
    if platform.startswith("win"):
        names += ["dwf.dll", "C:\\Windows\\System32\\dwf.dll"]
    elif platform.startswith("darwin"):
        names += ["/Library/Frameworks/dwf.framework/dwf", "dwf.framework/dwf"]
    else:
        names += ["libdwf.so", "/usr/lib/libdwf.so", "/usr/lib/digilent/waveforms/libdwf.so"]
    found = finder("dwf") if finder is not None else None
    if found is not None and found != "" and found not in names:
        names.append(found)
    return names


def load_library(
    loader: Loader | None = None,
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
    proc_version: str | None = None,
    finder: Callable[[str], str | None] | None = ctypes.util.find_library,
) -> Result[Any, DwfError]:
    """Load libdwf (env override, then per-OS names); Err(LIBRARY_MISSING) with per-OS fix steps."""
    load = loader if loader is not None else _DEFAULT_LOADER
    environ = os.environ if env is None else env
    plat = sys.platform if platform is None else platform
    names = candidate_names(plat, environ, finder)
    failures: list[str] = []
    for name in names:
        try:
            lib = load(name)
        except OSError as exc:
            _log.debug("dwf library %s not loadable: %s", name, exc)
            failures.append(f"{name}: {exc}")
            continue
        _log.info("dwf library loaded from %s", name)
        return Ok(lib)
    wsl = False
    if plat.startswith("linux"):
        wsl = is_wsl(_read_proc_version() if proc_version is None else proc_version)
    _log.error("dwf library not found on %s (wsl=%s); tried %d names", plat, wsl, len(names))
    return Err(
        DwfError(
            code=DwfCode.LIBRARY_MISSING,
            detail="; ".join(failures),
            steps=library_steps(plat, wsl),
        )
    )


def load_backend(
    loader: Loader | None = None,
    env: Mapping[str, str] | None = None,
    platform: str | None = None,
    proc_version: str | None = None,
) -> Result[CtypesBackend, DwfError]:
    """Load libdwf and wrap it in a CtypesBackend; never raises for a missing library."""
    lib = load_library(loader, env, platform, proc_version)
    if not isinstance(lib, Ok):
        return Err(lib.unwrap_err())
    return Ok(CtypesBackend(lib.unwrap()))


def _b(flag: bool) -> ctypes.c_int:
    """Marshal a bool as the C int the API expects."""
    return ctypes.c_int(1 if flag else 0)


class CtypesBackend:
    """DwfBackend over a loaded libdwf (or any object with the same FDwf* callables)."""

    def __init__(self, lib: Any) -> None:
        """Wrap `lib`, a ctypes library or an injected fake exposing FDwf* functions."""
        self._lib = lib

    # -- error mapping -----------------------------------------------------------------
    def _last_error(self, code: DwfCode, what: str) -> DwfError:
        """Build an Err value carrying FDwfGetLastErrorMsg/FDwfGetLastError text for `what`."""
        buf = ctypes.create_string_buffer(ERROR_MSG_LEN)
        erc = ctypes.c_int(0)
        msg = ""
        if self._lib.FDwfGetLastErrorMsg(buf):
            msg = buf.value.decode("ascii", errors="replace")
        if self._lib.FDwfGetLastError(ctypes.byref(erc)):
            _log.debug("%s last erc=%d", what, erc.value)
        err = DwfError(code=code, detail=f"{what}: {msg}" if msg else what, erc=erc.value)
        _log.error("dwf %s failed: %s (erc=%d)", what, msg, erc.value)
        return err

    def _call(
        self, name: str, *args: Any, code: DwfCode = DwfCode.CALL_FAILED
    ) -> Result[None, DwfError]:
        """Call FDwf `name`; a 0 return (DWF failure) maps to Err with the last error text."""
        _log.debug("dwf call %s", name)
        ok = getattr(self._lib, name)(*args)
        if not ok:
            return Err(self._last_error(code, name))
        return Ok(None)

    def _dcall(self, dev: OpenDevice, name: str, *args: Any) -> Result[None, DwfError]:
        """Call an FDwf function on a live device; Err(HANDLE_CLOSED) if the handle was consumed."""
        h = dev.native()
        if not isinstance(h, Ok):
            return Err(h.unwrap_err())
        return self._call(name, ctypes.c_int(h.unwrap()), *args)

    def _dout(self, dev: OpenDevice, name: str, out: Any, *args: Any) -> Result[None, DwfError]:
        """Call an FDwf getter whose last argument is the out-param `out` (passed by reference)."""
        return self._dcall(dev, name, *args, ctypes.byref(out))

    # -- library / enumeration ---------------------------------------------------------
    def version(self) -> Result[str, DwfError]:
        """Return the DWF library version string."""
        buf = ctypes.create_string_buffer(VERSION_LEN)
        done = self._call("FDwfGetVersion", buf)
        if not isinstance(done, Ok):
            return Err(done.unwrap_err())
        return Ok(buf.value.decode("ascii", errors="replace"))

    def set_on_close(self, mode: int) -> Result[None, DwfError]:
        """Set what devices do on close: 0 keep running, 1 stop, 2 shut down."""
        return self._call("FDwfParamSet", ctypes.c_int(int(DwfParam.ON_CLOSE)), ctypes.c_int(mode))

    def enumerate_devices(
        self, flt: EnumFilter = EnumFilter.ALL
    ) -> Result[list[DeviceInfo], DwfError]:
        """List attached devices matching `flt`."""
        count = ctypes.c_int(0)
        done = self._call("FDwfEnum", ctypes.c_int(int(flt)), ctypes.byref(count))
        if not isinstance(done, Ok):
            return Err(done.unwrap_err())
        out: list[DeviceInfo] = []
        for i in range(count.value):
            name = ctypes.create_string_buffer(NAME_LEN)
            serial = ctypes.create_string_buffer(NAME_LEN)
            devid = ctypes.c_int(0)
            rev = ctypes.c_int(0)
            for step in (
                self._call("FDwfEnumDeviceName", ctypes.c_int(i), name),
                self._call("FDwfEnumSN", ctypes.c_int(i), serial),
                self._call(
                    "FDwfEnumDeviceType", ctypes.c_int(i), ctypes.byref(devid), ctypes.byref(rev)
                ),
            ):
                if not isinstance(step, Ok):
                    return Err(step.unwrap_err())
            known = devid.value in DeviceId._value2member_map_
            out.append(
                DeviceInfo(
                    index=i,
                    name=name.value.decode("ascii", errors="replace"),
                    serial=serial.value.decode("ascii", errors="replace"),
                    device_id=DeviceId(devid.value) if known else None,
                )
            )
        _log.info("enumerated %d device(s)", len(out))
        return Ok(out)

    # -- open / close ------------------------------------------------------------------
    def open(self, index: int) -> Result[OpenDevice, DwfError]:
        """Open the device at `index` (-1 = first available); Err(DEVICE_NOT_FOUND) if none."""
        hdwf = ctypes.c_int(HDWF_NONE)
        done = self._call(
            "FDwfDeviceOpen", ctypes.c_int(index), ctypes.byref(hdwf), code=DwfCode.DEVICE_NOT_FOUND
        )
        if not isinstance(done, Ok):
            return Err(done.unwrap_err())
        if hdwf.value == HDWF_NONE:
            _log.error("FDwfDeviceOpen returned success with no handle")
            return Err(self._last_error(DwfCode.DEVICE_NOT_FOUND, "FDwfDeviceOpen"))
        _log.info("opened device index=%d hdwf=%d", index, hdwf.value)
        return Ok(OpenDevice(hdwf.value, FIRST_DEVICE if index < 0 else index))

    def close(self, dev: OpenDevice) -> Result[ClosedDevice, DwfError]:
        """Close `dev`, consuming the handle (it is consumed even if the native close fails)."""
        h = dev.native()
        if not isinstance(h, Ok):
            return Err(h.unwrap_err())
        closed = dev.consume()
        done = self._call("FDwfDeviceClose", ctypes.c_int(h.unwrap()))
        if not isinstance(done, Ok):
            return Err(done.unwrap_err())
        return closed

    def auto_configure(self, dev: OpenDevice, enable: bool) -> Result[None, DwfError]:
        """Enable or disable automatic reconfiguration on every setter call."""
        return self._dcall(dev, "FDwfDeviceAutoConfigureSet", _b(enable))

    # -- analog out --------------------------------------------------------------------
    def out_node_enable(
        self, dev: OpenDevice, ch: Channel, node: OutNode, enable: bool
    ) -> Result[None, DwfError]:
        """Enable or disable an analog out node."""
        return self._dcall(
            dev, "FDwfAnalogOutNodeEnableSet", ctypes.c_int(ch), ctypes.c_int(int(node)), _b(enable)
        )

    def out_node_function(
        self, dev: OpenDevice, ch: Channel, node: OutNode, func: WaveFunction
    ) -> Result[None, DwfError]:
        """Select the waveform of an analog out node (FUNC is an unsigned char)."""
        return self._dcall(
            dev,
            "FDwfAnalogOutNodeFunctionSet",
            ctypes.c_int(ch),
            ctypes.c_int(int(node)),
            ctypes.c_ubyte(int(func)),
        )

    def out_node_frequency(
        self, dev: OpenDevice, ch: Channel, node: OutNode, hz: float
    ) -> Result[None, DwfError]:
        """Set an analog out node frequency in hertz."""
        return self._dcall(
            dev,
            "FDwfAnalogOutNodeFrequencySet",
            ctypes.c_int(ch),
            ctypes.c_int(int(node)),
            ctypes.c_double(hz),
        )

    def out_node_amplitude(
        self, dev: OpenDevice, ch: Channel, node: OutNode, volts: float
    ) -> Result[None, DwfError]:
        """Set an analog out node amplitude in volts."""
        return self._dcall(
            dev,
            "FDwfAnalogOutNodeAmplitudeSet",
            ctypes.c_int(ch),
            ctypes.c_int(int(node)),
            ctypes.c_double(volts),
        )

    def out_node_offset(
        self, dev: OpenDevice, ch: Channel, node: OutNode, volts: float
    ) -> Result[None, DwfError]:
        """Set an analog out node offset in volts."""
        return self._dcall(
            dev,
            "FDwfAnalogOutNodeOffsetSet",
            ctypes.c_int(ch),
            ctypes.c_int(int(node)),
            ctypes.c_double(volts),
        )

    def out_configure(self, dev: OpenDevice, ch: Channel, start: bool) -> Result[None, DwfError]:
        """Apply analog out settings for `ch`, optionally starting generation."""
        return self._dcall(dev, "FDwfAnalogOutConfigure", ctypes.c_int(ch), _b(start))

    # -- analog in ---------------------------------------------------------------------
    def in_reset(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Reset the analog in instrument to defaults."""
        return self._dcall(dev, "FDwfAnalogInReset")

    def in_channel_enable(
        self, dev: OpenDevice, ch: Channel, enable: bool
    ) -> Result[None, DwfError]:
        """Enable or disable a scope channel."""
        return self._dcall(dev, "FDwfAnalogInChannelEnableSet", ctypes.c_int(ch), _b(enable))

    def in_channel_range(
        self, dev: OpenDevice, ch: Channel, volts: float
    ) -> Result[None, DwfError]:
        """Set a scope channel full-scale range in volts."""
        return self._dcall(
            dev, "FDwfAnalogInChannelRangeSet", ctypes.c_int(ch), ctypes.c_double(volts)
        )

    def in_channel_offset(
        self, dev: OpenDevice, ch: Channel, volts: float
    ) -> Result[None, DwfError]:
        """Set a scope channel offset in volts."""
        return self._dcall(
            dev, "FDwfAnalogInChannelOffsetSet", ctypes.c_int(ch), ctypes.c_double(volts)
        )

    def in_frequency(self, dev: OpenDevice, hz: float) -> Result[None, DwfError]:
        """Set the scope sample rate in hertz."""
        return self._dcall(dev, "FDwfAnalogInFrequencySet", ctypes.c_double(hz))

    def in_buffer_size(self, dev: OpenDevice, samples: int) -> Result[None, DwfError]:
        """Set the scope buffer length in samples."""
        return self._dcall(dev, "FDwfAnalogInBufferSizeSet", ctypes.c_int(samples))

    def in_acquisition_mode(self, dev: OpenDevice, mode: AcqMode) -> Result[None, DwfError]:
        """Select the scope acquisition mode."""
        return self._dcall(dev, "FDwfAnalogInAcquisitionModeSet", ctypes.c_int(int(mode)))

    def in_configure(
        self, dev: OpenDevice, reconfigure: bool, start: bool
    ) -> Result[None, DwfError]:
        """Apply scope settings and optionally start acquisition."""
        return self._dcall(dev, "FDwfAnalogInConfigure", _b(reconfigure), _b(start))

    def in_status(self, dev: OpenDevice, read_data: bool) -> Result[AcqState, DwfError]:
        """Poll the scope state (DwfState is an unsigned char), optionally latching data."""
        sts = ctypes.c_ubyte(0)
        done = self._dout(dev, "FDwfAnalogInStatus", sts, _b(read_data))
        if not isinstance(done, Ok):
            return Err(done.unwrap_err())
        try:
            return Ok(AcqState(sts.value))
        except ValueError:
            _log.error("unknown DwfState %d", sts.value)
            return Err(DwfError(code=DwfCode.BAD_RESPONSE, detail=f"unknown DwfState {sts.value}"))

    def in_data(self, dev: OpenDevice, ch: Channel, count: int) -> Result[list[float], DwfError]:
        """Return `count` volt samples of `ch` from the last status(read_data=True)."""
        buf = (ctypes.c_double * count)()
        done = self._dcall(
            dev, "FDwfAnalogInStatusData", ctypes.c_int(ch), buf, ctypes.c_int(count)
        )
        if not isinstance(done, Ok):
            return Err(done.unwrap_err())
        return Ok(list(buf))

    # -- analog IO ---------------------------------------------------------------------
    def io_enable(self, dev: OpenDevice, enable: bool) -> Result[None, DwfError]:
        """Set the analog IO master enable (power supplies)."""
        return self._dcall(dev, "FDwfAnalogIOEnableSet", _b(enable))

    def io_node_set(
        self, dev: OpenDevice, ch: Channel, node: IoNode, value: float
    ) -> Result[None, DwfError]:
        """Set an analog IO node value (for example a supply voltage)."""
        return self._dcall(
            dev,
            "FDwfAnalogIOChannelNodeSet",
            ctypes.c_int(ch),
            ctypes.c_int(node),
            ctypes.c_double(value),
        )

    def io_configure(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Apply analog IO settings."""
        return self._dcall(dev, "FDwfAnalogIOConfigure")

    def io_status(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Latch analog IO readings for io_node_status()."""
        return self._dcall(dev, "FDwfAnalogIOStatus")

    def io_node_status(self, dev: OpenDevice, ch: Channel, node: IoNode) -> Result[float, DwfError]:
        """Return the latched reading of an analog IO node."""
        value = ctypes.c_double(0.0)
        done = self._dout(
            dev, "FDwfAnalogIOChannelNodeStatus", value, ctypes.c_int(ch), ctypes.c_int(node)
        )
        if not isinstance(done, Ok):
            return Err(done.unwrap_err())
        return Ok(value.value)

    # -- digital IO --------------------------------------------------------------------
    def dio_output_enable(self, dev: OpenDevice, mask: int) -> Result[None, DwfError]:
        """Set which digital pins are outputs (bit mask)."""
        return self._dcall(dev, "FDwfDigitalIOOutputEnableSet", ctypes.c_uint(mask))

    def dio_output(self, dev: OpenDevice, mask: int) -> Result[None, DwfError]:
        """Set digital output pin states (bit mask)."""
        return self._dcall(dev, "FDwfDigitalIOOutputSet", ctypes.c_uint(mask))

    def dio_configure(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Apply digital IO settings."""
        return self._dcall(dev, "FDwfDigitalIOConfigure")

    def dio_status(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Latch digital input state for dio_input()."""
        return self._dcall(dev, "FDwfDigitalIOStatus")

    def dio_input(self, dev: OpenDevice) -> Result[int, DwfError]:
        """Return the latched digital input bit mask."""
        mask = ctypes.c_uint(0)
        done = self._dout(dev, "FDwfDigitalIOInputStatus", mask)
        if not isinstance(done, Ok):
            return Err(done.unwrap_err())
        return Ok(mask.value)
