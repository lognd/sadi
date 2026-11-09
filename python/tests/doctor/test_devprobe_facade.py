"""devprobe failure modes: a hostile sadi_py never raises out of the probes."""

# frob:ticket 01M6Z3095E9TR8FEQM7Y6MM2ZP

from __future__ import annotations

import errno
import sys
import types

import pytest

from sadi.doctor import devprobe


def _install(monkeypatch: pytest.MonkeyPatch, **attrs: object) -> None:
    base = {
        "ports": lambda: [types.SimpleNamespace(name="/dev/ttyUSB0", vid=0x0403)],
        "SessionConfig": lambda **kw: kw,
        "Handshake": types.SimpleNamespace(QUERY_ONLY=1),
    }
    base.update(attrs)
    monkeypatch.setitem(sys.modules, "sadi_py", types.SimpleNamespace(**base))


# frob:tests python/sadi/doctor/devprobe.py::probe_device
@pytest.mark.parametrize(
    ("exc", "status"),
    [
        (PermissionError(errno.EACCES, "denied"), "denied"),
        (OSError(errno.EBUSY, "busy"), "busy"),
        (OSError(errno.EIO, "unplugged"), "io-error"),
        (RuntimeError("panic"), "io-error"),
        (ValueError("garbage"), "io-error"),
    ],
)
def test_open_failures_are_classified(
    monkeypatch: pytest.MonkeyPatch, exc: Exception, status: str
) -> None:
    def _open(_p: str, _c: object) -> None:
        raise exc

    _install(monkeypatch, open_serial=_open)
    got = devprobe.probe_device(None, 0, False)
    assert got.open_status == status


# frob:tests python/sadi/doctor/devprobe.py::probe_device
def test_missing_binding_and_listing_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sadi_py", None)
    got = devprobe.probe_device(None, 0, False)
    assert got.open_status == "no-device" and "not importable" in got.open_detail

    def _boom() -> None:
        raise OSError(errno.EIO, "enum failed")

    _install(monkeypatch, ports=_boom)
    got = devprobe.probe_device(None, 0, False)
    assert got.open_status == "no-device" and "listing failed" in got.open_detail


# frob:tests python/sadi/doctor/devprobe.py::probe_device
def test_garbage_nan_and_stream_failure_closed_on_all_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []

    class Sess:
        def connect(self) -> None: ...
        def query(self) -> object:
            return types.SimpleNamespace(fw_version=1.0, state="DeviceState.BOOTED", state_byte=1)

        def start(self, _m: object) -> None: ...
        def read_block(self) -> object:
            raise OSError(errno.EIO, "unplugged mid-stream")

        def stop(self) -> None:
            raise RuntimeError("no ack")

        def close(self) -> None:
            closed.append("x")
            raise OSError("close also fails")

    _install(
        monkeypatch,
        open_serial=lambda _p, _c: Sess(),
        AdcMode=types.SimpleNamespace(IDEAL=0),
    )
    got = devprobe.probe_device(None, 1, False)
    assert got.stream_status == "error" and "unplugged" in got.stream_detail
    assert closed == ["x"]


# frob:tests python/sadi/doctor/devprobe.py::probe_sim
def test_probe_sim_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "sadi_py", None)
    assert devprobe.probe_sim().binding_ok is False

    def _bad(_n: str, _s: int) -> None:
        raise RuntimeError("panic")

    _install(monkeypatch, open_sim=_bad)
    got = devprobe.probe_sim()
    assert got.connect_ok is False and len(got.failed_scenarios) == len(devprobe.SCENARIO_NAMES)

    class TimeoutSess:
        def connect(self) -> None: ...
        def start(self, _m: object) -> None: ...
        def read_block(self) -> object:
            raise TimeoutError("read")

        def stop(self) -> None: ...
        def close(self) -> None: ...

    _install(
        monkeypatch, open_sim=lambda _n, _s: TimeoutSess(), AdcMode=types.SimpleNamespace(IDEAL=0)
    )
    got = devprobe.probe_sim()
    assert got.timed_out is True and got.connect_ok is False
