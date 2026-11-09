"""AD3 facade tests: no exception escapes CtypesBackend; every edge case is an Err value."""

# frob:ticket 01M6Z3092SGKVHQ3CZ98AMGV5D
from __future__ import annotations

import ctypes
import logging
from typing import Any

import pytest
from typani import Err, Ok

from sadi.bench.ad3 import (
    AcqMode,
    AcqState,
    Channel,
    CtypesBackend,
    DwfCode,
    OutNode,
    WaveFunction,
)
from sadi.bench.ad3.backend import OpenDevice, hint_for, wait_acquired
from sadi.bench.ad3.dll import _REGISTRY, close_all_open
from tests.bench.test_ad3_binding import FakeLib, _open

CH = Channel(0)


def _code(res: Any) -> DwfCode:
    """Assert `res` is an Err and return its code."""
    assert isinstance(res, Err), res
    code = res.unwrap_err().code
    assert isinstance(code, DwfCode)
    return code


class RaisingLib(FakeLib):
    """FakeLib whose named function raises the given exception."""

    def __init__(self, name: str, exc: BaseException) -> None:
        """Raise `exc` when `name` is called."""
        super().__init__()
        self.raises = (name, exc)

    def _behave(self, name: str, args: tuple[Any, ...]) -> int:
        """Raise for the configured function, else behave like FakeLib."""
        if name == self.raises[0]:
            raise self.raises[1]
        return super()._behave(name, args)


class NoSymbolLib:
    """A library exposing nothing (every FDwf symbol missing)."""

    def __getattr__(self, name: str) -> Any:
        """Always missing."""
        raise AttributeError(name)


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend._call
@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (ctypes.ArgumentError("bad"), DwfCode.BAD_ARGUMENT),
        (OverflowError("big"), DwfCode.OUT_OF_RANGE),
        (ValueError("v"), DwfCode.BAD_ARGUMENT),
        (OSError("dll gone"), DwfCode.FFI_ERROR),
        (UnicodeDecodeError("ascii", b"\xff", 0, 1, "x"), DwfCode.BAD_RESPONSE),
        (RuntimeError("weird"), DwfCode.UNEXPECTED),
    ],
)
def test_exceptions_map_to_distinct_codes(exc: BaseException, code: DwfCode) -> None:
    """Every exception a native call can raise becomes a specific Err."""
    be, dev = _open(FakeLib())
    be2 = CtypesBackend(RaisingLib("FDwfAnalogInReset", exc))
    dev2 = be2.open(0).unwrap()
    assert _code(be2.in_reset(dev2)) is code
    assert be.in_reset(dev).is_ok


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend._call
def test_missing_symbol_is_symbol_missing() -> None:
    """A library without an FDwf symbol yields SYMBOL_MISSING, not AttributeError."""
    be = CtypesBackend(NoSymbolLib())
    assert _code(be.version()) is DwfCode.SYMBOL_MISSING
    assert _code(be.enumerate_devices()) is DwfCode.SYMBOL_MISSING
    assert _code(be.open(0)) is DwfCode.SYMBOL_MISSING


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend._last_error
@pytest.mark.parametrize(
    ("erc", "msg", "code"),
    [
        (2, b"x", DwfCode.TIMEOUT),
        (3, b"x", DwfCode.BUSY),
        (4, b"x", DwfCode.NOT_SUPPORTED),
        (0x13, b"x", DwfCode.BAD_ARGUMENT),
        (1, b"Device was disconnected", DwfCode.DEVICE_LOST),
        (1, b"device in use by another process", DwfCode.BUSY),
        (1, b"mystery", DwfCode.CALL_FAILED),
    ],
)
def test_erc_and_message_classification(erc: int, msg: bytes, code: DwfCode) -> None:
    """Known dwfERC values and message markers pick the specific code."""

    class L(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            if name == "FDwfGetLastErrorMsg":
                args[0].value = msg
                return 1
            if name == "FDwfGetLastError":
                self._out(args[0]).value = erc
                return 1
            return super()._behave(name, args)

    lib = L()
    be, dev = _open(lib)
    lib.fail.add("FDwfAnalogInReset")
    assert _code(be.in_reset(dev)) is code


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend._last_error
def test_last_error_failure_does_not_escape() -> None:
    """If reading the last error itself raises, the original failure is still an Err."""
    lib = RaisingLib("FDwfGetLastError", OSError("x"))
    be, dev = _open(lib)
    lib.fail.add("FDwfAnalogInReset")
    assert _code(be.in_reset(dev)) is DwfCode.CALL_FAILED


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_frequency
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0, 0.0, 1e999, "1", None, True])
def test_bad_float_rejected_before_ffi(bad: Any) -> None:
    """Non-finite, non-positive or non-numeric rates never reach the FFI."""
    lib = FakeLib()
    be, dev = _open(lib)
    n = len(lib.calls)
    assert _code(be.in_frequency(dev, bad)) in {DwfCode.BAD_ARGUMENT, DwfCode.OUT_OF_RANGE}
    assert len(lib.calls) == n


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.out_node_amplitude
def test_huge_int_amplitude_is_out_of_range() -> None:
    """An int too large for a double is OUT_OF_RANGE, not OverflowError."""
    be, dev = _open(FakeLib())
    assert _code(be.out_node_amplitude(dev, CH, OutNode.CARRIER, 10**400)) is DwfCode.OUT_OF_RANGE
    assert _code(be.out_node_amplitude(dev, CH, OutNode.CARRIER, float("nan"))) is (
        DwfCode.BAD_ARGUMENT
    )


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.out_node_enable
def test_channel_and_node_ranges() -> None:
    """Channels and nodes outside their ranges are rejected before the call."""
    be, dev = _open(FakeLib())
    assert _code(be.out_node_enable(dev, Channel(-1), OutNode.CARRIER, True)) is (
        DwfCode.OUT_OF_RANGE
    )
    assert _code(be.out_node_enable(dev, Channel(99), OutNode.CARRIER, True)) is (
        DwfCode.OUT_OF_RANGE
    )
    assert _code(be.out_node_enable(dev, CH, 77, True)) is DwfCode.BAD_ARGUMENT  # ty: ignore[invalid-argument-type]
    assert _code(be.out_node_enable(dev, CH, OutNode.CARRIER, 1)) is DwfCode.BAD_ARGUMENT  # ty: ignore[invalid-argument-type]
    assert _code(be.out_node_function(dev, CH, OutNode.CARRIER, 250)) is (  # ty: ignore[invalid-argument-type]
        DwfCode.BAD_ARGUMENT
    )
    assert be.out_node_function(dev, CH, OutNode.CARRIER, WaveFunction.SINE).is_ok


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.dio_output
@pytest.mark.parametrize("mask", [-1, 2**32, 2**64])
def test_int_outside_c_range(mask: int) -> None:
    """Masks beyond 32 bits are rejected instead of silently wrapping."""
    be, dev = _open(FakeLib())
    assert _code(be.dio_output(dev, mask)) is DwfCode.OUT_OF_RANGE
    assert _code(be.dio_output_enable(dev, mask)) is DwfCode.OUT_OF_RANGE


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_buffer_size
@pytest.mark.parametrize("n", [0, -5, 2**31, 10**20])
def test_buffer_size_bounds(n: int) -> None:
    """Buffer sizes <= 0 or beyond the cap are rejected."""
    be, dev = _open(FakeLib())
    assert _code(be.in_buffer_size(dev, n)) is DwfCode.OUT_OF_RANGE


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_data
def test_in_data_count_validation() -> None:
    """Counts <= 0 or beyond the configured buffer are rejected before the FFI."""
    lib = FakeLib()
    be, dev = _open(lib)
    be.in_buffer_size(dev, 8).unwrap()
    for bad in (0, -1, 9, 2**40):
        assert _code(be.in_data(dev, CH, bad)) is DwfCode.OUT_OF_RANGE
    assert "FDwfAnalogInStatusData" not in lib.call_names()
    assert len(be.in_data(dev, CH, 8).unwrap()) == 8


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_data
def test_in_data_output_validation() -> None:
    """NaN/inf samples and short valid counts are BAD_RESPONSE."""

    class NanLib(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            r = super()._behave(name, args)
            if name == "FDwfAnalogInStatusData":
                args[2][1] = float("nan")
            return r

    be, dev = _open(NanLib())
    assert _code(be.in_data(dev, CH, 4)) is DwfCode.BAD_RESPONSE

    class ShortLib(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            if name == "FDwfAnalogInStatusSamplesValid":
                self._out(args[1]).value = 2
                return 1
            return super()._behave(name, args)

    be2, dev2 = _open(ShortLib())
    assert _code(be2.in_data(dev2, CH, 4)) is DwfCode.BAD_RESPONSE


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.in_status
def test_garbage_state_and_io_reading() -> None:
    """An unknown DwfState byte and a NaN IO reading are BAD_RESPONSE."""

    class L(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            if name == "FDwfAnalogInStatus":
                self._out(args[2]).value = 200
                return 1
            if name == "FDwfAnalogIOChannelNodeStatus":
                self._out(args[3]).value = float("inf")
                return 1
            return super()._behave(name, args)

    be, dev = _open(L())
    assert _code(be.in_status(dev, False)) is DwfCode.BAD_RESPONSE
    assert _code(be.io_node_status(dev, CH, 0)) is DwfCode.BAD_RESPONSE  # ty: ignore[invalid-argument-type]


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.enumerate_devices
def test_enumeration_garbage_and_busy() -> None:
    """Non-ASCII/empty names, absurd counts and busy devices are handled."""
    lib = FakeLib()
    lib.devices = [(b"\xff\xfe", b"SN:1", 10)]
    assert _code(CtypesBackend(lib).enumerate_devices()) is DwfCode.BAD_RESPONSE
    lib.devices = [(b"AD3", b"", 10)]
    assert _code(CtypesBackend(lib).enumerate_devices()) is DwfCode.BAD_RESPONSE

    class Many(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            if name == "FDwfEnum":
                self._out(args[1]).value = 100000
                return 1
            return super()._behave(name, args)

    assert _code(CtypesBackend(Many()).enumerate_devices()) is DwfCode.BAD_RESPONSE

    class Busy(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            if name == "FDwfEnumDeviceIsOpened":
                self._out(args[1]).value = 1
                return 1
            return super()._behave(name, args)

    infos = CtypesBackend(Busy()).enumerate_devices().unwrap()
    assert infos[0].in_use is True


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.open
def test_open_edge_cases() -> None:
    """Bad index, no handle returned and a busy device are Errs."""
    be = CtypesBackend(FakeLib())
    assert _code(be.open(10**9)) is DwfCode.OUT_OF_RANGE
    assert _code(be.open(-5)) is DwfCode.OUT_OF_RANGE

    class NoHandle(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            if name == "FDwfDeviceOpen":
                self._out(args[1]).value = 0
                return 1
            return super()._behave(name, args)

    assert _code(CtypesBackend(NoHandle()).open(0)) is DwfCode.DEVICE_NOT_FOUND

    class Busy(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            if name == "FDwfGetLastError":
                self._out(args[0]).value = 3
                return 1
            return super()._behave(name, args)

    lib = Busy()
    lib.fail.add("FDwfDeviceOpen")
    assert _code(CtypesBackend(lib).open(0)) is DwfCode.BUSY


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.close
def test_double_close_and_use_after_close() -> None:
    """Closing twice or using a closed device is HANDLE_CLOSED, never an exception."""
    be, dev = _open(FakeLib())
    assert be.close(dev).is_ok
    assert _code(be.close(dev)) is DwfCode.HANDLE_CLOSED
    assert _code(be.in_reset(dev)) is DwfCode.HANDLE_CLOSED
    assert _code(be.in_data(dev, CH, 1)) is DwfCode.HANDLE_CLOSED
    assert _code(be.in_status(dev, False)) is DwfCode.HANDLE_CLOSED


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.close
def test_native_close_failure_still_consumes_handle() -> None:
    """A failing native close reports Err but the handle cannot be reused."""
    lib = FakeLib()
    be, dev = _open(lib)
    lib.fail.add("FDwfDeviceClose")
    assert _code(be.close(dev)) is DwfCode.CALL_FAILED
    assert _code(be.in_reset(dev)) is DwfCode.HANDLE_CLOSED


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend._dcall
def test_device_lost_mid_acquisition_invalidates_handle() -> None:
    """A disconnect during polling is DEVICE_LOST and later calls see a closed handle."""

    class L(FakeLib):
        lost = False

        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            if name == "FDwfGetLastErrorMsg":
                args[0].value = b"The device was disconnected"
                return 1
            if name == "FDwfAnalogInStatus" and self.lost:
                return 0
            return super()._behave(name, args)

    lib = L()
    be, dev = _open(lib)
    assert be.in_status(dev, False).is_ok
    lib.lost = True
    assert _code(be.in_status(dev, False)) is DwfCode.DEVICE_LOST
    assert _code(be.in_status(dev, False)) is DwfCode.HANDLE_CLOSED
    assert _REGISTRY.count() == 0


# frob:tests python/sadi/bench/ad3/dll.py::close_all_open
def test_leaked_handle_closed_at_exit(caplog: pytest.LogCaptureFixture) -> None:
    """The atexit hook closes still-open handles and logs a warning."""
    lib = FakeLib()
    be, dev = _open(lib)
    with caplog.at_level(logging.WARNING, logger="sadi.bench.ad3.dll"):
        assert close_all_open() >= 1
    assert "FDwfDeviceClose" in lib.call_names()
    assert "leaked" in caplog.text
    assert _code(be.in_reset(dev)) is DwfCode.HANDLE_CLOSED
    assert close_all_open() == 0


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend.close_all
def test_backend_close_all_only_its_own() -> None:
    """close_all closes this backend's handles and tolerates a raising close."""
    lib = RaisingLib("FDwfDeviceClose", OSError("gone"))
    be, _ = _open(lib)
    assert be.close_all() == 1
    assert be.close_all() == 0


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend._call
def test_calls_are_serialized_by_lock() -> None:
    """Concurrent callers never overlap inside the FFI."""
    import threading
    import time

    active = 0
    peak = 0
    guard = threading.Lock()

    class L(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            nonlocal active, peak
            if name == "FDwfAnalogInReset":
                with guard:
                    active += 1
                    peak = max(peak, active)
                time.sleep(0.01)
                with guard:
                    active -= 1
                return 1
            return super()._behave(name, args)

    be, dev = _open(L())
    ts = [threading.Thread(target=be.in_reset, args=(dev,)) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert peak == 1


# frob:tests python/sadi/bench/ad3/backend.py::wait_acquired
def test_wait_acquired_ok_timeout_and_args() -> None:
    """Polling returns Ok on DONE, TIMEOUT when bounded, BAD_ARGUMENT on bad timings."""
    be, dev = _open(FakeLib())
    assert wait_acquired(be, dev).is_ok

    class Never(FakeLib):
        def _behave(self, name: str, args: tuple[Any, ...]) -> int:
            if name == "FDwfAnalogInStatus":
                self._out(args[2]).value = int(AcqState.ARMED)
                return 1
            return super()._behave(name, args)

    be2, dev2 = _open(Never())
    t = [0.0]

    def clock() -> float:
        t[0] += 0.5
        return t[0]

    res = wait_acquired(be2, dev2, timeout_s=2.0, clock=clock, sleep=lambda _s: None)
    assert _code(res) is DwfCode.TIMEOUT
    assert _code(wait_acquired(be, dev, timeout_s=float("nan"))) is DwfCode.BAD_ARGUMENT
    assert _code(wait_acquired(be, dev, timeout_s=-1.0)) is DwfCode.BAD_ARGUMENT
    assert _code(wait_acquired(be, dev, poll_s=0.0)) is DwfCode.BAD_ARGUMENT


# frob:tests python/sadi/bench/ad3/backend.py::hint_for
def test_every_code_has_a_hint() -> None:
    """hint_for returns numbered steps for every DwfCode."""
    for code in DwfCode:
        assert hint_for(code), code


# frob:tests python/sadi/bench/ad3/dll.py::CtypesBackend._call
def test_errors_are_logged(caplog: pytest.LogCaptureFixture) -> None:
    """Every error path emits an ERROR record on the module logger."""
    be = CtypesBackend(NoSymbolLib())
    with caplog.at_level(logging.ERROR, logger="sadi.bench.ad3.dll"):
        be.version()
    assert any(r.levelno == logging.ERROR for r in caplog.records)


def test_unused_imports_keep_types() -> None:
    """Keep typing-only names referenced."""
    assert AcqMode and OpenDevice
    assert isinstance(Ok(1), Ok)
