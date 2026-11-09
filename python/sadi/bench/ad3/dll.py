"""The single ctypes edge: lazy libdwf discovery and CtypesBackend, the real DwfBackend."""

# frob:ticket 01M6WSPW5XB6P5V3PR5SHEH6FP
# frob:ticket 01M6Z3092SGKVHQ3CZ98AMGV5D
from __future__ import annotations

import atexit
import ctypes
import ctypes.util
import math
import os
import sys
import threading
from collections.abc import Callable, Mapping
from enum import IntEnum
from typing import Any, TypeVar

from typani import Err, Ok, Result, propagate

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
    INT_MAX,
    INT_MIN,
    MAX_BUFFER_SAMPLES,
    MAX_CHANNELS,
    MAX_DEVICES,
    MAX_NODES,
    NAME_LEN,
    UINT_MAX,
    VERSION_LEN,
    AcqMode,
    AcqState,
    Channel,
    DeviceId,
    DwfErc,
    DwfParam,
    EnumFilter,
    IoNode,
    OutNode,
    WaveFunction,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = [
    "CtypesBackend",
    "candidate_names",
    "close_all_open",
    "is_wsl",
    "load_backend",
    "load_library",
]

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


_E = TypeVar("_E", bound=IntEnum)

# erc -> code for values the DWF documents; anything else keeps the caller's default code.
_ERC_CODES: dict[int, DwfCode] = {
    int(DwfErc.API_LOCK_TIMEOUT): DwfCode.TIMEOUT,
    int(DwfErc.ALREADY_OPENED): DwfCode.BUSY,
    int(DwfErc.NOT_SUPPORTED): DwfCode.NOT_SUPPORTED,
    int(DwfErc.INVALID_PARAMETER0): DwfCode.BAD_ARGUMENT,
    int(DwfErc.INVALID_PARAMETER1): DwfCode.BAD_ARGUMENT,
    int(DwfErc.INVALID_PARAMETER2): DwfCode.BAD_ARGUMENT,
    int(DwfErc.INVALID_PARAMETER3): DwfCode.BAD_ARGUMENT,
    int(DwfErc.INVALID_PARAMETER4): DwfCode.BAD_ARGUMENT,
}
# The library gives no erc for unplug, so its message text is the only signal.
_LOST_MARKERS = ("disconnect", "unplug", "lost", "no longer", "removed", "not connected")
_BUSY_MARKERS = ("in use", "busy", "already open", "another process", "opened by")


def _mk(code: DwfCode, detail: str, erc: int | None = None) -> DwfError:
    """Build a DwfError and log it once at the boundary."""
    _log.error("dwf %s: %s", code.name, detail)
    return DwfError(code=code, detail=detail, erc=erc)


def _classify(default: DwfCode, erc: int, msg: str) -> DwfCode:
    """Map a native erc (then message text) to the most specific DwfCode, else `default`."""
    mapped = _ERC_CODES.get(erc)
    if mapped is not None:
        return mapped
    low = msg.lower()
    if default is not DwfCode.DEVICE_NOT_FOUND and any(m in low for m in _LOST_MARKERS):
        return DwfCode.DEVICE_LOST
    if any(m in low for m in _BUSY_MARKERS):
        return DwfCode.BUSY
    return default


def _number(value: object, what: str) -> Result[float, DwfError]:
    """Accept only a finite real number (not bool/str/None)."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        return Err(
            _mk(DwfCode.BAD_ARGUMENT, f"{what} must be a number, got {type(value).__name__}")
        )
    try:
        as_float = float(value)
    except OverflowError:
        return Err(_mk(DwfCode.OUT_OF_RANGE, f"{what} too large for a double"))
    if not math.isfinite(as_float):
        return Err(_mk(DwfCode.BAD_ARGUMENT, f"{what} must be finite, got {value!r}"))
    return Ok(as_float)


def _positive(value: object, what: str, allow_zero: bool = False) -> Result[float, DwfError]:
    """A finite number that is > 0 (or >= 0 when `allow_zero`)."""
    num = _number(value, what)
    if isinstance(num, Err):
        return num
    v = num.unwrap()
    if v < 0 or (v == 0 and not allow_zero):
        return Err(
            _mk(DwfCode.OUT_OF_RANGE, f"{what} must be {'>=' if allow_zero else '>'} 0: {v!r}")
        )
    return Ok(v)


def _int(value: object, what: str, lo: int = INT_MIN, hi: int = INT_MAX) -> Result[int, DwfError]:
    """An int (not bool) within [lo, hi]; OUT_OF_RANGE otherwise."""
    if isinstance(value, bool) or not isinstance(value, int):
        return Err(_mk(DwfCode.BAD_ARGUMENT, f"{what} must be an int, got {type(value).__name__}"))
    if not lo <= value <= hi:
        return Err(_mk(DwfCode.OUT_OF_RANGE, f"{what}={value} outside [{lo}, {hi}]"))
    return Ok(int(value))


def _chan(ch: object, what: str = "channel") -> Result[int, DwfError]:
    """A channel index in [0, MAX_CHANNELS)."""
    return _int(ch, what, 0, MAX_CHANNELS - 1)


def _node(node: object) -> Result[int, DwfError]:
    """A node index in [0, MAX_NODES)."""
    return _int(node, "node", 0, MAX_NODES - 1)


def _flag(value: object, what: str) -> Result[ctypes.c_int, DwfError]:
    """Marshal a strict bool as the C int the API expects."""
    if not isinstance(value, bool):
        return Err(_mk(DwfCode.BAD_ARGUMENT, f"{what} must be a bool, got {type(value).__name__}"))
    return Ok(ctypes.c_int(1 if value else 0))


def _member(value: object, cls: type[_E], what: str) -> Result[int, DwfError]:
    """Require `value` to be a member of enum `cls` (or its int value); return the int."""
    if isinstance(value, bool) or not isinstance(value, int):
        return Err(_mk(DwfCode.BAD_ARGUMENT, f"{what} must be a {cls.__name__}"))
    try:
        return Ok(int(cls(value)))
    except ValueError:
        return Err(_mk(DwfCode.BAD_ARGUMENT, f"{what}={value} is not a valid {cls.__name__}"))


def _text(raw: bytes, what: str) -> Result[str, DwfError]:
    """Strictly decode a C string: ASCII, printable, non-empty; else BAD_RESPONSE."""
    try:
        text = raw.decode("ascii").strip()
    except UnicodeDecodeError:
        return Err(_mk(DwfCode.BAD_RESPONSE, f"{what} is not ASCII: {raw[:16]!r}"))
    if text == "" or not text.isprintable():
        return Err(_mk(DwfCode.BAD_RESPONSE, f"{what} is empty or unprintable: {text[:16]!r}"))
    return Ok(text)


class _OpenRegistry:
    """Process-wide set of live native handles so none leaks past interpreter exit."""

    def __init__(self) -> None:
        """Start empty."""
        self._lock = threading.Lock()
        self._live: dict[int, tuple[Any, OpenDevice]] = {}

    def add(self, lib: Any, dev: OpenDevice, hdwf: int) -> None:
        """Track an opened handle."""
        with self._lock:
            self._live[hdwf] = (lib, dev)

    def discard(self, hdwf: int) -> None:
        """Stop tracking `hdwf` (it was closed or lost)."""
        with self._lock:
            self._live.pop(hdwf, None)

    def count(self) -> int:
        """Number of tracked handles."""
        with self._lock:
            return len(self._live)

    def close_all(self, lib: Any | None = None) -> int:
        """Best-effort FDwfDeviceClose of every tracked handle (of `lib` if given); never raises."""
        with self._lock:
            items = [(h, lb, d) for h, (lb, d) in self._live.items() if lib is None or lb is lib]
            for h, _, _ in items:
                del self._live[h]
        for h, lb, d in items:
            _log.warning("closing leaked dwf handle %d (device index=%d)", h, d.index)
            try:
                lb.FDwfDeviceClose(ctypes.c_int(h))
            except Exception as exc:  # noqa: BLE001 - exit path must not raise
                _log.error("closing leaked handle %d failed: %s", h, exc)
            consumed = d.consume()
            if isinstance(consumed, Err):
                _log.debug("leaked handle %d was already consumed", h)
        return len(items)


_REGISTRY = _OpenRegistry()


def close_all_open() -> int:
    """Close every still-open DWF handle in this process; the atexit hook."""
    return _REGISTRY.close_all()


atexit.register(close_all_open)


class CtypesBackend:
    """DwfBackend over a loaded libdwf (or any object with the same FDwf* callables).

    This is the facade: it validates inputs, serializes FFI calls, and converts every library
    failure, missing symbol and Python exception into a `Result` error; nothing escapes.
    """

    def __init__(self, lib: Any) -> None:
        """Wrap `lib`, a ctypes library or an injected fake exposing FDwf* functions."""
        self._lib = lib
        self._lock = threading.RLock()
        self._buffers: dict[int, int] = {}

    def close_all(self) -> int:
        """Close every handle this backend opened that is still live; returns how many."""
        with self._lock:
            self._buffers.clear()
            return _REGISTRY.close_all(self._lib)

    # -- error mapping -----------------------------------------------------------------
    def _last_error(self, code: DwfCode, what: str) -> DwfError:
        """Build an Err value from FDwfGetLastError(Msg); classified by erc then message."""
        msg = ""
        erc = 0
        try:
            buf = ctypes.create_string_buffer(ERROR_MSG_LEN)
            erc_c = ctypes.c_int(0)
            if self._lib.FDwfGetLastErrorMsg(buf):
                msg = buf.value.decode("ascii", errors="replace").strip()
            if self._lib.FDwfGetLastError(ctypes.byref(erc_c)):
                erc = erc_c.value
        except Exception as exc:  # noqa: BLE001 - error reporting must not itself raise
            _log.warning("could not read dwf last error after %s: %s", what, exc)
        final = _classify(code, erc, msg)
        return _mk(final, f"{what}: {msg}" if msg else what, erc)

    def _call(
        self, name: str, *args: Any, code: DwfCode = DwfCode.CALL_FAILED
    ) -> Result[None, DwfError]:
        """Call FDwf `name` under the lock; 0 return, missing symbol or any exception -> Err."""
        with self._lock:
            fn = getattr(self._lib, name, None)
            if fn is None:
                return Err(_mk(DwfCode.SYMBOL_MISSING, f"libdwf has no {name}"))
            _log.debug("dwf call %s", name)
            try:
                ok = fn(*args)
            except ctypes.ArgumentError as exc:
                return Err(_mk(DwfCode.BAD_ARGUMENT, f"{name}: {exc}"))
            except OverflowError as exc:
                return Err(_mk(DwfCode.OUT_OF_RANGE, f"{name}: {exc}"))
            except UnicodeDecodeError as exc:
                return Err(_mk(DwfCode.BAD_RESPONSE, f"{name}: undecodable text: {exc}"))
            except (ValueError, TypeError) as exc:
                return Err(_mk(DwfCode.BAD_ARGUMENT, f"{name}: {exc}"))
            except OSError as exc:
                return Err(_mk(DwfCode.FFI_ERROR, f"{name}: {exc}"))
            except Exception as exc:  # noqa: BLE001  # typani: ignore[TYP007]
                return Err(_mk(DwfCode.UNEXPECTED, f"{name}: {type(exc).__name__}: {exc}"))
            if not ok:
                return Err(self._last_error(code, name))
            return Ok(None)

    def _probe(self, name: str, *args: Any) -> bool:
        """Call an optional FDwf function; True only when present and successful."""
        if getattr(self._lib, name, None) is None:
            _log.debug("optional dwf function %s absent", name)
            return False
        return isinstance(self._call(name, *args), Ok)

    def _mark_lost(self, dev: OpenDevice, hdwf: int) -> None:
        """The device vanished: best-effort native close, consume the handle, stop tracking."""
        _log.error("device index=%d lost; invalidating handle %d", dev.index, hdwf)
        closed = self._call("FDwfDeviceClose", ctypes.c_int(hdwf))
        if isinstance(closed, Err):
            _log.debug("native close of lost device failed (expected)")
        consumed = dev.consume()
        if isinstance(consumed, Err):
            _log.debug("lost device handle already consumed")
        _REGISTRY.discard(hdwf)
        self._buffers.pop(hdwf, None)

    def _dcall(self, dev: OpenDevice, name: str, *args: Any) -> Result[None, DwfError]:
        """Call an FDwf function on a live device; HANDLE_CLOSED if consumed, handle lost-device."""
        h = dev.native()
        if isinstance(h, Err):
            return Err(h.unwrap_err())
        with self._lock:
            res = self._call(name, ctypes.c_int(h.unwrap()), *args)
            if isinstance(res, Err) and res.unwrap_err().code is DwfCode.DEVICE_LOST:
                self._mark_lost(dev, h.unwrap())
            return res

    def _dout(self, dev: OpenDevice, name: str, out: Any, *args: Any) -> Result[None, DwfError]:
        """Call an FDwf getter whose last argument is the out-param `out` (passed by reference)."""
        return self._dcall(dev, name, *args, ctypes.byref(out))

    # -- library / enumeration ---------------------------------------------------------
    @propagate
    def version(self) -> Result[str, DwfError]:
        """Return the DWF library version string."""
        buf = ctypes.create_string_buffer(VERSION_LEN)
        self._call("FDwfGetVersion", buf).unwrap()
        return _text(buf.value, "version")

    @propagate
    def set_on_close(self, mode: int) -> Result[None, DwfError]:
        """Set what devices do on close: 0 keep running, 1 stop, 2 shut down."""
        m = _int(mode, "on-close mode", 0, 2).unwrap()
        return self._call("FDwfParamSet", ctypes.c_int(int(DwfParam.ON_CLOSE)), ctypes.c_int(m))

    @propagate
    def enumerate_devices(
        self, flt: EnumFilter = EnumFilter.ALL
    ) -> Result[list[DeviceInfo], DwfError]:
        """List attached devices matching `flt`, flagging ones another process has open."""
        flt_v = _int(int(flt), "filter", 0, INT_MAX).unwrap()
        with self._lock:
            count = ctypes.c_int(0)
            self._call("FDwfEnum", ctypes.c_int(flt_v), ctypes.byref(count)).unwrap()
            if not 0 <= count.value <= MAX_DEVICES:
                return Err(_mk(DwfCode.BAD_RESPONSE, f"device count {count.value} is implausible"))
            out: list[DeviceInfo] = []
            for i in range(count.value):
                out.append(self._enum_one(i).unwrap())
        _log.info("enumerated %d device(s)", len(out))
        return Ok(out)

    @propagate
    def _enum_one(self, i: int) -> Result[DeviceInfo, DwfError]:
        """Read name, serial, type and in-use flag of enumerated device `i`."""
        name = ctypes.create_string_buffer(NAME_LEN)
        serial = ctypes.create_string_buffer(NAME_LEN)
        devid = ctypes.c_int(0)
        rev = ctypes.c_int(0)
        opened = ctypes.c_int(0)
        self._call("FDwfEnumDeviceName", ctypes.c_int(i), name).unwrap()
        self._call("FDwfEnumSN", ctypes.c_int(i), serial).unwrap()
        self._call(
            "FDwfEnumDeviceType", ctypes.c_int(i), ctypes.byref(devid), ctypes.byref(rev)
        ).unwrap()
        in_use = (
            opened.value != 0
            if self._probe("FDwfEnumDeviceIsOpened", ctypes.c_int(i), ctypes.byref(opened))
            else None
        )
        name_s = _text(name.value, f"device {i} name").unwrap()
        serial_s = _text(serial.value, f"device {i} serial").unwrap()
        known = devid.value in DeviceId._value2member_map_
        return Ok(
            DeviceInfo(
                index=i,
                name=name_s,
                serial=serial_s,
                device_id=DeviceId(devid.value) if known else None,
                in_use=in_use,
            )
        )

    # -- open / close ------------------------------------------------------------------
    @propagate
    def open(self, index: int) -> Result[OpenDevice, DwfError]:
        """Open the device at `index` (-1 = first available); Err(DEVICE_NOT_FOUND/BUSY) if not."""
        idx = _int(index, "device index", FIRST_DEVICE, MAX_DEVICES - 1).unwrap()
        with self._lock:
            hdwf = ctypes.c_int(HDWF_NONE)
            done = self._call(
                "FDwfDeviceOpen",
                ctypes.c_int(idx),
                ctypes.byref(hdwf),
                code=DwfCode.DEVICE_NOT_FOUND,
            )
            if isinstance(done, Err):
                return Err(done.unwrap_err())
            if hdwf.value == HDWF_NONE:
                _log.error("FDwfDeviceOpen returned success with no handle")
                return Err(self._last_error(DwfCode.DEVICE_NOT_FOUND, "FDwfDeviceOpen"))
            if hdwf.value < 0:
                if isinstance(self._call("FDwfDeviceClose", hdwf), Err):
                    _log.debug("closing bogus handle failed")
                return Err(_mk(DwfCode.BAD_RESPONSE, f"FDwfDeviceOpen gave handle {hdwf.value}"))
            dev = OpenDevice(hdwf.value, FIRST_DEVICE if idx < 0 else idx)
            _REGISTRY.add(self._lib, dev, hdwf.value)
            _log.info("opened device index=%d hdwf=%d", idx, hdwf.value)
            return Ok(dev)

    def close(self, dev: OpenDevice) -> Result[ClosedDevice, DwfError]:
        """Close `dev`, consuming the handle (it is consumed even if the native close fails)."""
        h = dev.native()
        if isinstance(h, Err):
            return Err(h.unwrap_err())
        with self._lock:
            closed = dev.consume()
            _REGISTRY.discard(h.unwrap())
            self._buffers.pop(h.unwrap(), None)
            done = self._call("FDwfDeviceClose", ctypes.c_int(h.unwrap()))
            if isinstance(done, Err):
                return Err(done.unwrap_err())
            return closed

    @propagate
    def auto_configure(self, dev: OpenDevice, enable: bool) -> Result[None, DwfError]:
        """Enable or disable automatic reconfiguration on every setter call."""
        return self._dcall(dev, "FDwfDeviceAutoConfigureSet", _flag(enable, "enable").unwrap())

    # -- analog out --------------------------------------------------------------------
    @propagate
    def out_node_enable(
        self, dev: OpenDevice, ch: Channel, node: OutNode, enable: bool
    ) -> Result[None, DwfError]:
        """Enable or disable an analog out node."""
        c = _chan(ch).unwrap()
        n = _member(node, OutNode, "node").unwrap()
        e = _flag(enable, "enable").unwrap()
        return self._dcall(dev, "FDwfAnalogOutNodeEnableSet", ctypes.c_int(c), ctypes.c_int(n), e)

    @propagate
    def out_node_function(
        self, dev: OpenDevice, ch: Channel, node: OutNode, func: WaveFunction
    ) -> Result[None, DwfError]:
        """Select the waveform of an analog out node (FUNC is an unsigned char)."""
        c = _chan(ch).unwrap()
        n = _member(node, OutNode, "node").unwrap()
        f = _member(func, WaveFunction, "function").unwrap()
        return self._dcall(
            dev,
            "FDwfAnalogOutNodeFunctionSet",
            ctypes.c_int(c),
            ctypes.c_int(n),
            ctypes.c_ubyte(f),
        )

    @propagate
    def out_node_frequency(
        self, dev: OpenDevice, ch: Channel, node: OutNode, hz: float
    ) -> Result[None, DwfError]:
        """Set an analog out node frequency in hertz."""
        c = _chan(ch).unwrap()
        n = _member(node, OutNode, "node").unwrap()
        f = _positive(hz, "frequency", allow_zero=True).unwrap()
        return self._dcall(
            dev,
            "FDwfAnalogOutNodeFrequencySet",
            ctypes.c_int(c),
            ctypes.c_int(n),
            ctypes.c_double(f),
        )

    @propagate
    def out_node_amplitude(
        self, dev: OpenDevice, ch: Channel, node: OutNode, volts: float
    ) -> Result[None, DwfError]:
        """Set an analog out node amplitude in volts."""
        c = _chan(ch).unwrap()
        n = _member(node, OutNode, "node").unwrap()
        v = _number(volts, "amplitude").unwrap()
        return self._dcall(
            dev,
            "FDwfAnalogOutNodeAmplitudeSet",
            ctypes.c_int(c),
            ctypes.c_int(n),
            ctypes.c_double(v),
        )

    @propagate
    def out_node_offset(
        self, dev: OpenDevice, ch: Channel, node: OutNode, volts: float
    ) -> Result[None, DwfError]:
        """Set an analog out node offset in volts."""
        c = _chan(ch).unwrap()
        n = _member(node, OutNode, "node").unwrap()
        v = _number(volts, "offset").unwrap()
        return self._dcall(
            dev, "FDwfAnalogOutNodeOffsetSet", ctypes.c_int(c), ctypes.c_int(n), ctypes.c_double(v)
        )

    @propagate
    def out_configure(self, dev: OpenDevice, ch: Channel, start: bool) -> Result[None, DwfError]:
        """Apply analog out settings for `ch`, optionally starting generation."""
        c = _chan(ch).unwrap()
        s = _flag(start, "start").unwrap()
        return self._dcall(dev, "FDwfAnalogOutConfigure", ctypes.c_int(c), s)

    # -- analog in ---------------------------------------------------------------------
    def in_reset(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Reset the analog in instrument to defaults."""
        return self._dcall(dev, "FDwfAnalogInReset")

    @propagate
    def in_channel_enable(
        self, dev: OpenDevice, ch: Channel, enable: bool
    ) -> Result[None, DwfError]:
        """Enable or disable a scope channel."""
        c = _chan(ch).unwrap()
        e = _flag(enable, "enable").unwrap()
        return self._dcall(dev, "FDwfAnalogInChannelEnableSet", ctypes.c_int(c), e)

    @propagate
    def in_channel_range(
        self, dev: OpenDevice, ch: Channel, volts: float
    ) -> Result[None, DwfError]:
        """Set a scope channel full-scale range in volts (> 0)."""
        c = _chan(ch).unwrap()
        v = _positive(volts, "range").unwrap()
        return self._dcall(dev, "FDwfAnalogInChannelRangeSet", ctypes.c_int(c), ctypes.c_double(v))

    @propagate
    def in_channel_offset(
        self, dev: OpenDevice, ch: Channel, volts: float
    ) -> Result[None, DwfError]:
        """Set a scope channel offset in volts."""
        c = _chan(ch).unwrap()
        v = _number(volts, "offset").unwrap()
        return self._dcall(dev, "FDwfAnalogInChannelOffsetSet", ctypes.c_int(c), ctypes.c_double(v))

    @propagate
    def in_frequency(self, dev: OpenDevice, hz: float) -> Result[None, DwfError]:
        """Set the scope sample rate in hertz (> 0)."""
        f = _positive(hz, "sample rate").unwrap()
        return self._dcall(dev, "FDwfAnalogInFrequencySet", ctypes.c_double(f))

    @propagate
    def in_buffer_size(self, dev: OpenDevice, samples: int) -> Result[None, DwfError]:
        """Set the scope buffer length in samples (1..MAX_BUFFER_SAMPLES)."""
        n = _int(samples, "buffer size", 1, MAX_BUFFER_SAMPLES).unwrap()
        done = self._dcall(dev, "FDwfAnalogInBufferSizeSet", ctypes.c_int(n))
        if isinstance(done, Ok):
            self._buffers[dev.native().unwrap()] = n
        return done

    @propagate
    def in_acquisition_mode(self, dev: OpenDevice, mode: AcqMode) -> Result[None, DwfError]:
        """Select the scope acquisition mode."""
        m = _member(mode, AcqMode, "mode").unwrap()
        return self._dcall(dev, "FDwfAnalogInAcquisitionModeSet", ctypes.c_int(m))

    @propagate
    def in_configure(
        self, dev: OpenDevice, reconfigure: bool, start: bool
    ) -> Result[None, DwfError]:
        """Apply scope settings and optionally start acquisition."""
        r = _flag(reconfigure, "reconfigure").unwrap()
        s = _flag(start, "start").unwrap()
        return self._dcall(dev, "FDwfAnalogInConfigure", r, s)

    @propagate
    def in_status(self, dev: OpenDevice, read_data: bool) -> Result[AcqState, DwfError]:
        """Poll the scope state (DwfState is an unsigned char), optionally latching data."""
        flag = _flag(read_data, "read_data").unwrap()
        sts = ctypes.c_ubyte(0)
        self._dout(dev, "FDwfAnalogInStatus", sts, flag).unwrap()
        try:
            return Ok(AcqState(sts.value))
        except ValueError:
            return Err(_mk(DwfCode.BAD_RESPONSE, f"unknown DwfState {sts.value}"))

    @propagate
    def in_data(self, dev: OpenDevice, ch: Channel, count: int) -> Result[list[float], DwfError]:
        """Return `count` finite volt samples of `ch` from the last status(read_data=True)."""
        c = _chan(ch).unwrap()
        h = dev.native().unwrap()
        limit = self._buffers.get(h, MAX_BUFFER_SAMPLES)
        n = _int(count, "sample count", 1, limit).unwrap()
        buf = (ctypes.c_double * n)()
        with self._lock:
            valid = ctypes.c_int(0)
            self._dcall(
                dev, "FDwfAnalogInStatusData", ctypes.c_int(c), buf, ctypes.c_int(n)
            ).unwrap()
            if self._probe("FDwfAnalogInStatusSamplesValid", ctypes.c_int(h), ctypes.byref(valid)):
                if valid.value < n:
                    return Err(
                        _mk(DwfCode.BAD_RESPONSE, f"asked {n} samples but only {valid.value} valid")
                    )
        samples = list(buf)
        bad = next((i for i, v in enumerate(samples) if not math.isfinite(v)), None)
        if bad is not None:
            return Err(_mk(DwfCode.BAD_RESPONSE, f"sample {bad} of ch {c} is {samples[bad]!r}"))
        return Ok(samples)

    # -- analog IO ---------------------------------------------------------------------
    @propagate
    def io_enable(self, dev: OpenDevice, enable: bool) -> Result[None, DwfError]:
        """Set the analog IO master enable (power supplies)."""
        return self._dcall(dev, "FDwfAnalogIOEnableSet", _flag(enable, "enable").unwrap())

    @propagate
    def io_node_set(
        self, dev: OpenDevice, ch: Channel, node: IoNode, value: float
    ) -> Result[None, DwfError]:
        """Set an analog IO node value (for example a supply voltage)."""
        c = _chan(ch).unwrap()
        n = _node(node).unwrap()
        v = _number(value, "value").unwrap()
        return self._dcall(
            dev, "FDwfAnalogIOChannelNodeSet", ctypes.c_int(c), ctypes.c_int(n), ctypes.c_double(v)
        )

    def io_configure(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Apply analog IO settings."""
        return self._dcall(dev, "FDwfAnalogIOConfigure")

    def io_status(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Latch analog IO readings for io_node_status()."""
        return self._dcall(dev, "FDwfAnalogIOStatus")

    @propagate
    def io_node_status(self, dev: OpenDevice, ch: Channel, node: IoNode) -> Result[float, DwfError]:
        """Return the latched, finite reading of an analog IO node."""
        c = _chan(ch).unwrap()
        n = _node(node).unwrap()
        value = ctypes.c_double(0.0)
        self._dout(
            dev, "FDwfAnalogIOChannelNodeStatus", value, ctypes.c_int(c), ctypes.c_int(n)
        ).unwrap()
        if not math.isfinite(value.value):
            return Err(_mk(DwfCode.BAD_RESPONSE, f"io reading ch {c} node {n} is {value.value!r}"))
        return Ok(value.value)

    # -- digital IO --------------------------------------------------------------------
    @propagate
    def dio_output_enable(self, dev: OpenDevice, mask: int) -> Result[None, DwfError]:
        """Set which digital pins are outputs (32-bit mask)."""
        m = _int(mask, "mask", 0, UINT_MAX).unwrap()
        return self._dcall(dev, "FDwfDigitalIOOutputEnableSet", ctypes.c_uint(m))

    @propagate
    def dio_output(self, dev: OpenDevice, mask: int) -> Result[None, DwfError]:
        """Set digital output pin states (32-bit mask)."""
        m = _int(mask, "mask", 0, UINT_MAX).unwrap()
        return self._dcall(dev, "FDwfDigitalIOOutputSet", ctypes.c_uint(m))

    def dio_configure(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Apply digital IO settings."""
        return self._dcall(dev, "FDwfDigitalIOConfigure")

    def dio_status(self, dev: OpenDevice) -> Result[None, DwfError]:
        """Latch digital input state for dio_input()."""
        return self._dcall(dev, "FDwfDigitalIOStatus")

    @propagate
    def dio_input(self, dev: OpenDevice) -> Result[int, DwfError]:
        """Return the latched digital input bit mask."""
        mask = ctypes.c_uint(0)
        self._dout(dev, "FDwfDigitalIOInputStatus", mask).unwrap()
        return Ok(mask.value)
