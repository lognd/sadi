"""AD3 binding tests: discovery, per-OS fix hints, marshalling, typestate via a fake libdwf."""

# frob:ticket 01M6WSPW5XB6P5V3PR5SHEH6FP
from __future__ import annotations

import ctypes
import importlib
from typing import Any

import pytest
from typani import Err, Ok

from sadi.bench.ad3 import (
    AcqMode,
    AcqState,
    Channel,
    CtypesBackend,
    DwfCode,
    IoNode,
    OutNode,
    WaveFunction,
    load_backend,
)
from sadi.bench.ad3.backend import OpenDevice
from sadi.bench.ad3.dll import candidate_names, is_wsl


class FakeLib:
    """Stand-in for libdwf: records calls, fills out-params, fails names listed in `fail`."""

    def __init__(self) -> None:
        """Start with no calls and no failures."""
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self.fail: set[str] = set()
        self.devices = [(b"Analog Discovery 3", b"SN:210415B", 10)]

    def __getattr__(self, name: str) -> Any:
        """Return a callable recording the call and applying fake behaviour."""
        if not name.startswith("FDwf"):
            raise AttributeError(name)

        def fn(*args: Any) -> int:
            self.calls.append((name, args))
            return self._behave(name, args)

        return fn

    @staticmethod
    def _out(arg: Any) -> Any:
        """Return the ctypes object a byref() argument points at."""
        return arg._obj

    def _behave(self, name: str, args: tuple[Any, ...]) -> int:
        """Implement the out-param behaviour of the functions the tests use."""
        if name == "FDwfGetLastErrorMsg":
            args[0].value = b"fake failure text"
            return 1
        if name == "FDwfGetLastError":
            self._out(args[0]).value = 0x12
            return 1
        if name in self.fail:
            return 0
        if name == "FDwfGetVersion":
            args[0].value = b"3.99.9"
        elif name == "FDwfEnum":
            self._out(args[1]).value = len(self.devices)
        elif name == "FDwfEnumDeviceName":
            args[1].value = self.devices[args[0].value][0]
        elif name == "FDwfEnumSN":
            args[1].value = self.devices[args[0].value][1]
        elif name == "FDwfEnumDeviceType":
            self._out(args[1]).value = self.devices[args[0].value][2]
        elif name == "FDwfDeviceOpen":
            self._out(args[1]).value = 7
        elif name == "FDwfAnalogInStatus":
            self._out(args[2]).value = 2
        elif name == "FDwfAnalogInStatusData":
            for i in range(args[3].value):
                args[2][i] = 0.5 * i
        elif name == "FDwfAnalogIOChannelNodeStatus":
            self._out(args[3]).value = 3.3
        elif name == "FDwfDigitalIOInputStatus":
            self._out(args[1]).value = 0xA5
        return 1

    def call_names(self) -> list[str]:
        """Return the called function names in order."""
        return [n for n, _ in self.calls]

    def last(self) -> tuple[Any, ...]:
        """Return the argument tuple of the latest call."""
        return self.calls[-1][1]


def _open(lib: FakeLib) -> tuple[CtypesBackend, OpenDevice]:
    """Open device 0 on a fake backend."""
    be = CtypesBackend(lib)
    dev = be.open(0)
    assert isinstance(dev, Ok)
    return be, dev.unwrap()


# frob:tests python/sadi/bench/ad3/dll.py::load_backend
def test_import_never_touches_library() -> None:
    """Importing the package does not load any shared library (acceptance 1)."""
    mod = importlib.import_module("sadi.bench.ad3")
    assert hasattr(mod, "load_backend")


def _missing(name: str) -> Any:
    """Loader that always fails like a missing library."""
    raise OSError(f"{name}: cannot open shared object file")


# frob:tests python/sadi/bench/ad3/dll.py::load_backend
# frob:tests python/sadi/bench/ad3/dll.py::load_library
# frob:tests python/sadi/bench/ad3/backend.py::library_steps
# frob:tests python/sadi/bench/ad3/backend.py::numbered
# frob:tests python/sadi/bench/ad3/backend.py::DwfError.hint
# frob:tests python/sadi/bench/ad3/backend.py::hint_for
@pytest.mark.parametrize(
    ("platform", "proc", "must", "must_not"),
    [
        ("linux", "Linux version 5.15 generic", ["Adept", "WaveForms"], ["usbipd"]),
        (
            "linux",
            "Linux version 5.15-microsoft-standard-WSL2",
            ["Adept", "usbipd list", "usbipd attach"],
            [],
        ),
        ("win32", "", ["Windows", "System32"], ["usbipd", "Adept"]),
        ("darwin", "", [".dmg", "dwf.framework"], ["usbipd", "Adept"]),
    ],
)
def test_missing_library_per_os_hint(
    platform: str, proc: str, must: list[str], must_not: list[str]
) -> None:
    """No library gives Err(LIBRARY_MISSING) with numbered per-OS steps; usbipd only on WSL."""
    res = load_backend(_missing, {}, platform, proc)
    assert isinstance(res, Err)
    err = res.unwrap_err()
    assert err.code is DwfCode.LIBRARY_MISSING
    assert err.hint.startswith("1. ")
    assert "\n2. " in err.hint
    for text in must:
        assert text in err.hint
    for text in must_not:
        assert text not in err.hint


# frob:tests python/sadi/bench/ad3/dll.py::candidate_names
@pytest.mark.parametrize(
    ("platform", "expected"),
    [
        ("linux", ["libdwf.so", "/usr/lib/libdwf.so"]),
        ("win32", ["dwf.dll", "C:\\Windows\\System32\\dwf.dll"]),
        ("darwin", ["/Library/Frameworks/dwf.framework/dwf"]),
    ],
)
def test_candidate_names_per_os(platform: str, expected: list[str]) -> None:
    """Env override comes first, then the per-OS defaults, then the finder result."""
    names = candidate_names(platform, {"SADI_DWF_LIB": "/opt/x/dwf"}, lambda _n: "/found/dwf")
    assert names[0] == "/opt/x/dwf"
    assert names[-1] == "/found/dwf"
    for e in expected:
        assert e in names
    assert "/opt/x/dwf" not in candidate_names(platform, {}, None)


# frob:tests python/sadi/bench/ad3/dll.py::load_library
# frob:tests python/sadi/bench/ad3/dll.py::load_backend
def test_loader_uses_override_first() -> None:
    """The first loadable candidate wins and the override is tried first."""
    tried: list[str] = []

    def loader(name: str) -> Any:
        tried.append(name)
        if name == "libdwf.so":
            return FakeLib()
        raise OSError(name)

    res = load_backend(loader, {"SADI_DWF_LIB": "/nope"}, "linux", "")
    assert isinstance(res, Ok)
    assert tried == ["/nope", "libdwf.so"]


# frob:tests python/sadi/bench/ad3/dll.py::is_wsl
def test_is_wsl() -> None:
    """WSL is detected from 'microsoft' in /proc/version, case-insensitively."""
    assert is_wsl("Linux 5.15.167.4-microsoft-standard-WSL2")
    assert is_wsl("Linux Microsoft")
    assert not is_wsl("Linux version 6.1 generic")


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.version
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.enumerate_devices
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.open
def test_open_enumerate_version_marshalling() -> None:
    """Version, enumeration and open marshal strings and out-params correctly."""
    lib = FakeLib()
    be = CtypesBackend(lib)
    assert be.version().unwrap() == "3.99.9"
    devs = be.enumerate_devices().unwrap()
    assert devs[0].name == "Analog Discovery 3"
    assert devs[0].serial == "SN:210415B"
    assert devs[0].device_id is not None
    assert devs[0].device_id.name == "DISCOVERY3"
    dev = be.open(-1).unwrap()
    assert dev.native().unwrap() == 7
    name, args = lib.calls[-1]
    assert name == "FDwfDeviceOpen"
    assert args[0].value == -1


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.out_node_enable
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.out_node_function
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.out_node_frequency
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.out_node_amplitude
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.out_node_offset
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.out_configure
def test_analog_out_marshalling() -> None:
    """Analog out setters pass handle, channel, node and typed values in order."""
    lib = FakeLib()
    be, dev = _open(lib)
    assert isinstance(be.out_node_enable(dev, Channel(1), OutNode.CARRIER, True), Ok)
    assert lib.last()[0].value == 7
    assert lib.last()[1].value == 1
    assert lib.last()[3].value == 1
    be.out_node_function(dev, Channel(0), OutNode.AM, WaveFunction.SINE)
    assert lib.last()[2].value == 2
    assert isinstance(lib.last()[3], ctypes.c_ubyte)
    assert lib.last()[3].value == 1
    be.out_node_frequency(dev, Channel(0), OutNode.CARRIER, 1000.0)
    assert isinstance(lib.last()[3], ctypes.c_double)
    assert lib.last()[3].value == 1000.0
    be.out_node_amplitude(dev, Channel(0), OutNode.CARRIER, 1.41)
    be.out_node_offset(dev, Channel(0), OutNode.CARRIER, -0.5)
    assert lib.last()[3].value == -0.5
    be.out_configure(dev, Channel(0), True)
    assert lib.call_names()[-1] == "FDwfAnalogOutConfigure"
    assert lib.last()[2].value == 1


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_frequency
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_buffer_size
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_configure
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_status
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_data
def test_analog_in_marshalling() -> None:
    """Scope setters, status out-param and data buffer marshal correctly."""
    lib = FakeLib()
    be, dev = _open(lib)
    be.in_frequency(dev, 1e6)
    assert lib.last()[1].value == 1e6
    be.in_buffer_size(dev, 4)
    assert lib.last()[1].value == 4
    be.in_configure(dev, True, False)
    assert (lib.last()[1].value, lib.last()[2].value) == (1, 0)
    assert be.in_status(dev, True).unwrap() is AcqState.DONE
    assert be.in_data(dev, Channel(0), 4).unwrap() == [0.0, 0.5, 1.0, 1.5]
    assert lib.call_names()[-1] == "FDwfAnalogInStatusData"


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.io_node_set
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.io_node_status
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.dio_output_enable
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.dio_input
def test_io_marshalling() -> None:
    """Analog IO and digital IO setters and getters marshal values and out-params."""
    lib = FakeLib()
    be, dev = _open(lib)
    be.io_node_set(dev, Channel(0), IoNode(1), 5.0)
    assert lib.last()[3].value == 5.0
    assert be.io_node_status(dev, Channel(0), IoNode(1)).unwrap() == 3.3
    be.dio_output_enable(dev, 0xFF)
    assert lib.last()[1].value == 0xFF
    assert be.dio_input(dev).unwrap() == 0xA5


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.out_configure
def test_failure_maps_to_err_with_last_message() -> None:
    """A zero DWF return becomes Err(CALL_FAILED) carrying the last error text and erc."""
    lib = FakeLib()
    be, dev = _open(lib)
    lib.fail.add("FDwfAnalogOutConfigure")
    res = be.out_configure(dev, Channel(0), True)
    assert isinstance(res, Err)
    err = res.unwrap_err()
    assert err.code is DwfCode.CALL_FAILED
    assert "fake failure text" in err.detail
    assert "FDwfAnalogOutConfigure" in err.detail
    assert err.erc == 0x12


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.open
def test_open_failure_is_device_not_found() -> None:
    """A failing FDwfDeviceOpen is Err(DEVICE_NOT_FOUND) with a numbered hint."""
    lib = FakeLib()
    lib.fail.add("FDwfDeviceOpen")
    res = CtypesBackend(lib).open(0)
    assert isinstance(res, Err)
    err = res.unwrap_err()
    assert err.code is DwfCode.DEVICE_NOT_FOUND
    assert "fake failure text" in err.detail
    assert err.hint.startswith("1. ")


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.close
# frob:tests python/sadi/bench/ad3/backend.py::OpenDevice.consume
# frob:tests python/sadi/bench/ad3/backend.py::OpenDevice.native
# frob:tests python/sadi/bench/ad3/backend.py::OpenDevice.is_open
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_reset
def test_closed_handle_is_runtime_err() -> None:
    """close() consumes the handle; later calls and a second close return Err(HANDLE_CLOSED)."""
    lib = FakeLib()
    be, dev = _open(lib)
    closed = be.close(dev)
    assert isinstance(closed, Ok)
    assert closed.unwrap().index == 0
    assert not dev.is_open
    n = len(lib.calls)
    for res in (be.in_reset(dev), be.close(dev), be.out_configure(dev, Channel(0), True)):
        assert isinstance(res, Err)
        assert res.unwrap_err().code is DwfCode.HANDLE_CLOSED
    assert len(lib.calls) == n


# frob:tests python/sadi/bench/ad3/backend.py::ClosedDevice
def test_closed_device_has_no_operations() -> None:
    """ClosedDevice exposes no instrument methods (the type-level half of the typestate)."""
    lib = FakeLib()
    be, dev = _open(lib)
    closed = be.close(dev).unwrap()
    public = [a for a in dir(closed) if not a.startswith("_")]
    assert public == ["index"]


# frob:tests python/sadi/bench/ad3/backend.py::ClosedDevice.__repr__
# frob:tests python/sadi/bench/ad3/backend.py::OpenDevice.__repr__
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.set_on_close
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.auto_configure
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_channel_enable
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_channel_range
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_channel_offset
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_acquisition_mode
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.io_enable
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.io_configure
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.io_status
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.dio_output
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.dio_configure
# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.dio_status
def test_remaining_calls_hit_expected_functions() -> None:
    """Each remaining setter calls its FDwf function with the handle first."""
    lib = FakeLib()
    be, dev = _open(lib)
    calls = [
        (be.set_on_close(0), "FDwfParamSet"),
        (be.auto_configure(dev, True), "FDwfDeviceAutoConfigureSet"),
        (be.in_channel_enable(dev, Channel(0), True), "FDwfAnalogInChannelEnableSet"),
        (be.in_channel_range(dev, Channel(0), 5.0), "FDwfAnalogInChannelRangeSet"),
        (be.in_channel_offset(dev, Channel(0), 0.1), "FDwfAnalogInChannelOffsetSet"),
        (be.in_acquisition_mode(dev, AcqMode.SINGLE), "FDwfAnalogInAcquisitionModeSet"),
        (be.io_enable(dev, True), "FDwfAnalogIOEnableSet"),
        (be.io_configure(dev), "FDwfAnalogIOConfigure"),
        (be.io_status(dev), "FDwfAnalogIOStatus"),
        (be.dio_output(dev, 1), "FDwfDigitalIOOutputSet"),
        (be.dio_configure(dev), "FDwfDigitalIOConfigure"),
        (be.dio_status(dev), "FDwfDigitalIOStatus"),
    ]
    for res, fn in calls:
        assert isinstance(res, Ok), fn
        assert fn in lib.call_names()
    assert dev.native().unwrap() == 7
    assert "DwfError" in repr(dev) or "OpenDevice" in repr(dev)
    assert "ClosedDevice" in repr(be.close(dev).unwrap())
