"""High-level AD3 wrapper: typestate, context manager, Result errors, over FakeDwf."""

# frob:ticket 01M6Z335HGJVJD2MG8NZ37V6TP
from __future__ import annotations

import pytest
from typani import Err, Ok

from sadi.bench.ad3 import Ad3Closed, DwfCode, WaveFunction, open_ad3
from sadi.bench.ad3.fake import FakeDwf


def _session():  # noqa: ANN202
    return open_ad3(FakeDwf()).unwrap()


# frob:tests python/sadi/bench/ad3/device.py::open_ad3
# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.__exit__
# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.__enter__
# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.__init__
# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.is_open
# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.version
def test_context_manager_closes() -> None:
    """Leaving the with block closes the device so it can be reopened."""
    be = FakeDwf()
    with open_ad3(be).unwrap() as s:
        assert s.is_open
    assert not s.is_open
    assert isinstance(open_ad3(be), Ok)


# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.close
def test_close_twice_is_handle_closed() -> None:
    """Close consumes the session; later calls return HANDLE_CLOSED, never raise."""
    s = _session()
    closed = s.close().unwrap()
    assert isinstance(closed, Ad3Closed)
    err = s.close().unwrap_err()
    assert err.code is DwfCode.HANDLE_CLOSED and err.hint
    assert s.version().is_ok
    r = s.capture(0, 1000.0, 16)
    assert isinstance(r, Err) and r.unwrap_err().code is DwfCode.HANDLE_CLOSED


# frob:tests python/sadi/bench/ad3/device.py::Ad3Closed.open
# frob:tests python/sadi/bench/ad3/device.py::Ad3Closed.enumerate
# frob:tests python/sadi/bench/ad3/device.py::Ad3Closed.__repr__
# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.__repr__
def test_open_failure_is_err_and_reusable() -> None:
    """Opening a missing index is Err(DEVICE_NOT_FOUND) and the Ad3Closed stays usable."""
    closed = Ad3Closed(FakeDwf(), index=5)
    err = closed.open().unwrap_err()
    assert err.code is DwfCode.DEVICE_NOT_FOUND and "Plug" in err.hint
    assert closed.enumerate().unwrap()[0].name


# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.wave
# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.capture
def test_wave_loopback_capture() -> None:
    """A DC wave on out 0 is captured on scope 0 of the fake."""
    with _session() as s:
        s.wave(0, WaveFunction.DC, 1.0, 0.0, offset_v=1.0).unwrap()
        data = s.capture(0, 1000.0, 32).unwrap()
        assert len(data) == 32 and all(abs(v - 1.0) < 0.1 for v in data)
        s.stop_wave(0).unwrap()


# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.capture
def test_capture_rejects_bad_args() -> None:
    """Bad sample counts and rates are BAD_ARGUMENT before any device call."""
    with _session() as s:
        for samples, hz in ((0, 1000.0), (-1, 1000.0), (8, float("nan")), (8, 0.0)):
            err = s.capture(0, hz, samples).unwrap_err()
            assert err.code is DwfCode.BAD_ARGUMENT


# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.set_supply
# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.supplies_off
def test_supplies() -> None:
    """Supplies accept positive/negative and reject unknown sides."""
    with _session() as s:
        s.set_supply("positive", 3.3).unwrap()
        s.set_supply("negative", -3.3).unwrap()
        assert s.set_supply("middle", 1.0).unwrap_err().code is DwfCode.BAD_ARGUMENT
        s.supplies_off().unwrap()


# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.dio_write
# frob:tests python/sadi/bench/ad3/device.py::Ad3Session.dio_read
def test_dio_roundtrip() -> None:
    """Driven digital pins read back."""
    with _session() as s:
        s.dio_write(0b1111, 0b0101).unwrap()
        assert s.dio_read().unwrap() == 0b0101


# frob:tests python/sadi/bench/ad3/device.py::Ad3Closed.from_library
def test_from_library_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """Without a library the Err is LIBRARY_MISSING with numbered steps."""
    monkeypatch.setenv("SADI_DWF_LIB", "/nonexistent/libdwf.so")
    res = Ad3Closed.from_library()
    if isinstance(res, Err):
        assert res.unwrap_err().code is DwfCode.LIBRARY_MISSING
        assert res.unwrap_err().hint.startswith("1.")


def test_version_enumerate_and_repr() -> None:
    """version() and enumerate() succeed on the fake; reprs name the state."""
    closed = Ad3Closed(FakeDwf())
    assert len(closed.enumerate().unwrap()) >= 1
    assert "Ad3Closed" in repr(closed)
    with closed.open().unwrap() as s:
        assert s.version().unwrap()
        assert "Ad3Session" in repr(s)
