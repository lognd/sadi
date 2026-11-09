"""Tests for sadi.core.devfacade: every third-party failure mode becomes a typed Err value."""

# frob:ticket 01M6Z3095E9TR8FEQM7Y6MM2ZP

from __future__ import annotations

import errno
import sys
import types
from collections.abc import Callable

import numpy as np
import pytest
from typani import Err, Ok

from sadi.core import devfacade as df
from sadi.core.errors import DeviceCode, hint_for


class _SadiError(Exception):
    """Stand-in for sadi_py.SadiError."""

    def __init__(self, kind: str, detail: str = "boom") -> None:
        super().__init__(kind)
        self.kind = kind
        self.detail = detail


class _Panic(BaseException):  # noqa: N818 - mirrors pyo3_runtime.PanicException (BaseException)
    """Stand-in for a PyO3 panic."""


@pytest.fixture
def fake_sp(monkeypatch: pytest.MonkeyPatch) -> types.SimpleNamespace:
    """Install a fake sadi_py in sys.modules."""
    mod = types.SimpleNamespace(
        SadiError=_SadiError, AdcMode=types.SimpleNamespace(DLL_COMPATIBLE="dll")
    )
    monkeypatch.setitem(sys.modules, "sadi_py", mod)
    return mod


def _raiser(exc: BaseException) -> Callable[[], None]:
    def _go() -> None:
        raise exc

    return _go


# frob:tests python/sadi/core/devfacade.py::guard
# frob:tests python/sadi/core/devfacade.py::to_device_error
@pytest.mark.parametrize(
    ("exc", "code"),
    [
        (PermissionError(errno.EACCES, "denied"), DeviceCode.PERMISSION_DENIED),
        (OSError(errno.EPERM, "nope"), DeviceCode.PERMISSION_DENIED),
        (OSError(errno.EBUSY, "Device or resource busy"), DeviceCode.BUSY),
        (OSError(0, "port is in use by pid 4"), DeviceCode.BUSY),
        (FileNotFoundError(errno.ENOENT, "no such port"), DeviceCode.NOT_FOUND),
        (TimeoutError("slow"), DeviceCode.TIMEOUT),
        (BrokenPipeError(), DeviceCode.DISCONNECTED),
        (ConnectionResetError(), DeviceCode.DISCONNECTED),
        (OSError(errno.EIO, "unplugged mid-stream"), DeviceCode.DISCONNECTED),
        (OSError("generic io"), DeviceCode.DISCONNECTED),
        (ImportError("no wheel"), DeviceCode.BINDING_MISSING),
        (UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"), DeviceCode.BAD_DATA),
        (ValueError("short read"), DeviceCode.BAD_DATA),
        (TypeError("x"), DeviceCode.BAD_DATA),
        (AttributeError("no field"), DeviceCode.BAD_DATA),
        (OverflowError("big"), DeviceCode.BAD_DATA),
        (RuntimeError("pyo3"), DeviceCode.INTERNAL),
        (MemoryError(), DeviceCode.INTERNAL),
        (_Panic("rust panic"), DeviceCode.INTERNAL),
    ],
)
def test_every_failure_mode_is_an_err(exc: BaseException, code: DeviceCode) -> None:
    res = df.guard("op", _raiser(exc))
    assert isinstance(res, Err)
    assert res.danger_err.code is code
    assert hint_for(res.danger_err.code)


# frob:tests python/sadi/core/devfacade.py::guard
@pytest.mark.parametrize("exc", [KeyboardInterrupt(), SystemExit(1), df.SpentPhaseError("x")])
def test_exits_and_programmer_bugs_propagate(exc: BaseException) -> None:
    with pytest.raises(type(exc)):
        df.guard("op", _raiser(exc))


# frob:tests python/sadi/core/devfacade.py::guard
def test_guard_ok_passes_value() -> None:
    assert df.guard("op", lambda: 3) == Ok(3)


# frob:tests python/sadi/core/devfacade.py::to_device_error
@pytest.mark.parametrize(
    ("kind", "detail", "code"),
    [
        ("transport_timeout", "t", DeviceCode.TIMEOUT),
        ("read_timeout", "t", DeviceCode.TIMEOUT),
        ("transport_io", "Permission denied (os error 13)", DeviceCode.PERMISSION_DENIED),
        ("transport_io", "Device or resource busy", DeviceCode.BUSY),
        ("transport_closed", "gone", DeviceCode.DISCONNECTED),
        ("config", "no such port", DeviceCode.NOT_FOUND),
        ("codec", "bad crc", DeviceCode.BAD_DATA),
        ("tap", "x", DeviceCode.PROTOCOL),
        ("never-heard-of-it", "x", DeviceCode.PROTOCOL),
    ],
)
def test_sadi_py_kinds_map(
    fake_sp: types.SimpleNamespace, kind: str, detail: str, code: DeviceCode
) -> None:
    res = df.guard("op", _raiser(_SadiError(kind, detail)))
    assert isinstance(res, Err) and res.danger_err.code is code


# frob:tests python/sadi/core/devfacade.py::guard
@pytest.mark.parametrize("kind", sorted(df.PROGRAMMER_KINDS))
def test_phase_contract_kinds_reraise(fake_sp: types.SimpleNamespace, kind: str) -> None:
    with pytest.raises(_SadiError):
        df.guard("op", _raiser(_SadiError(kind)))


# frob:tests python/sadi/core/devfacade.py::binding
def test_binding_missing_is_err(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sadi_py", None)  # import raises ImportError
    res = df.binding()
    assert isinstance(res, Err) and res.danger_err.code is DeviceCode.BINDING_MISSING


# frob:tests python/sadi/core/devfacade.py::binding
def test_binding_import_panic_is_err(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(_name: str) -> None:
        raise _Panic("init panic")

    monkeypatch.setattr(df.importlib, "import_module", _boom)
    res = df.binding()
    assert isinstance(res, Err) and res.danger_err.code is DeviceCode.BINDING_MISSING


# frob:tests python/sadi/core/devfacade.py::binding
# frob:tests python/sadi/core/devfacade.py::default_adc_mode
def test_binding_and_default_mode_ok(fake_sp: types.SimpleNamespace) -> None:
    assert df.binding() == Ok(fake_sp)
    assert df.default_adc_mode() == Ok("dll")


# frob:tests python/sadi/core/devfacade.py::default_adc_mode
def test_default_mode_without_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sadi_py", None)
    assert df.default_adc_mode().is_err


# frob:tests python/sadi/core/devfacade.py::close_quietly
def test_close_quietly_never_raises() -> None:
    assert df.close_quietly("c", lambda: None) == Ok(None)
    res = df.close_quietly("c", _raiser(OSError(errno.EIO, "gone")))
    assert isinstance(res, Err) and res.danger_err.code is DeviceCode.DISCONNECTED


def _block(volts: list[float], n: int | None = None) -> types.SimpleNamespace:
    v = np.array(volts, dtype=float)
    return types.SimpleNamespace(
        n_samples=len(v) if n is None else n, volts=v, adc_raw=np.zeros((len(v), 4), np.uint16)
    )


# frob:tests python/sadi/core/devfacade.py::check_block
def test_check_block_accepts_good_and_empty() -> None:
    good = _block([0.1, -4.9])
    assert df.check_block(good) == Ok(good)
    assert df.check_block(_block([])).is_ok


# frob:tests python/sadi/core/devfacade.py::check_block
@pytest.mark.parametrize(
    "bad",
    [
        _block([0.0, float("nan")]),
        _block([float("inf")]),
        _block([0.0, 1.0], n=3),
        _block([0.0], n=-1),
        types.SimpleNamespace(n_samples=1),  # missing columns
        object(),
    ],
)
def test_check_block_rejects_garbage(bad: object) -> None:
    res = df.check_block(bad)
    assert isinstance(res, Err) and res.danger_err.code is DeviceCode.BAD_DATA


# frob:tests python/sadi/core/devfacade.py::to_device_error
def test_every_device_code_has_a_hint() -> None:
    for code in DeviceCode:
        assert hint_for(code)
