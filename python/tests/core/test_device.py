"""Tests for sadi.core.device: service lifecycle, reader queue overflow, reconnect, status."""

# frob:ticket 01M6W7R2NWFTQBK7FRWGX511CP

from __future__ import annotations

import time
from collections.abc import Callable

import pytest
from typani import Err, Ok, Result

sp = pytest.importorskip("sadi_py", reason="sadi_py extension not built (maturin develop)")

from sadi.core import device as dev  # noqa: E402
from sadi.core.errors import DeviceCode, DeviceError  # noqa: E402
from sadi.core.phases import Disconnected  # noqa: E402


def _svc(
    queue_blocks: int = dev.DEFAULT_QUEUE_BLOCKS,
    backoff: dev.Backoff | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dev.DeviceService:
    src = dev.DeviceSource(kind="sim", scenario="clean", seed=1)
    return dev.DeviceService(src, queue_blocks=queue_blocks, backoff=backoff, sleep=sleep)


# frob:tests python/sadi/core/device.py::DeviceService.__init__
# frob:tests python/sadi/core/device.py::DeviceService.open
# frob:tests python/sadi/core/device.py::DeviceService.status
# frob:tests python/sadi/core/device.py::DeviceService.start_streaming
# frob:tests python/sadi/core/device.py::DeviceService.next_block
# frob:tests python/sadi/core/device.py::DeviceService.stop_streaming
# frob:tests python/sadi/core/device.py::DeviceService.close
# frob:tests python/sadi/core/device.py::DeviceService._reader
def test_stream_and_stop_against_simulator() -> None:
    svc = _svc()
    assert svc.status == dev.DeviceStatus.ERROR
    assert svc.open() == Ok(None)
    assert svc.status == dev.DeviceStatus.SIMULATED
    assert svc.start_streaming().is_ok
    blocks = [svc.next_block(timeout=5.0).unwrap() for _ in range(3)]
    assert all(b is not None and b.n_samples > 0 for b in blocks)
    rest = svc.stop_streaming().unwrap()
    assert rest and rest[-1] is not None
    assert svc.status == dev.DeviceStatus.SIMULATED
    # can stream again after a stop
    assert svc.start_streaming().is_ok
    assert svc.next_block(timeout=5.0).unwrap() is not None
    svc.stop_streaming().unwrap()
    svc.close()


# frob:tests python/sadi/core/device.py::DeviceService._set_fault
# frob:tests python/sadi/core/device.py::DeviceService.fault
# frob:tests python/sadi/core/device.py::ReaderOverflow
# frob:tests python/sadi/core/device.py::ReaderOverflow.hint
def test_slow_consumer_overflows_loudly_without_dropping() -> None:
    svc = _svc(queue_blocks=2)
    svc.open().unwrap()
    svc.start_streaming().unwrap()
    deadline = time.monotonic() + 10
    while svc.fault is None and time.monotonic() < deadline:
        time.sleep(0.02)
    assert isinstance(svc.fault, dev.ReaderOverflow)
    assert svc.status == dev.DeviceStatus.ERROR
    # queued blocks and the held block come out first, then the loud error; none vanish
    got = 0
    while True:
        res = svc.next_block(timeout=0.2)
        if isinstance(res, Err):
            assert isinstance(res.danger_err, dev.ReaderOverflow)
            assert res.danger_err.hint
            break
        assert res.danger_ok is not None
        got += 1
    assert got == 3  # 2 queued + the held one
    svc.close()


# frob:tests python/sadi/core/device.py::DeviceService.reconnect
# frob:tests python/sadi/core/device.py::Backoff.delay
# frob:tests python/sadi/core/device.py::DeviceService._open_once
def test_reconnect_backs_off_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {"n": 0}
    real = dev.open_sim

    def flaky(
        scenario: str, seed: int | None = None, cfg: sp.SessionConfig | None = None
    ) -> Result[Disconnected, DeviceError]:
        calls["n"] += 1
        if calls["n"] < 3:
            return Err(DeviceError(code=DeviceCode.DISCONNECTED, detail="unplugged"))
        return real(scenario, seed, cfg)

    monkeypatch.setattr(dev, "open_sim", flaky)
    sleeps: list[float] = []
    svc = _svc(backoff=dev.Backoff(attempts=4, base_s=0.1, max_s=0.15), sleep=sleeps.append)
    assert svc.reconnect() == Ok(None)
    assert sleeps == [0.1, 0.15]
    assert svc.status == dev.DeviceStatus.SIMULATED
    svc.close()


def test_reconnect_gives_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        dev, "open_sim", lambda *a, **k: Err(DeviceError(code=DeviceCode.TIMEOUT, detail="t"))
    )
    sleeps: list[float] = []
    svc = _svc(backoff=dev.Backoff(attempts=3, base_s=1.0), sleep=sleeps.append)
    res = svc.reconnect()
    assert isinstance(res, Err) and res.danger_err.code == DeviceCode.TIMEOUT
    assert sleeps == [1.0, 2.0]
    assert svc.status == dev.DeviceStatus.ERROR


# frob:tests python/sadi/core/device.py::DeviceService._resolve_port
def test_serial_autodetect_no_ftdi(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dev, "list_ports", lambda: Ok([]))
    svc = dev.DeviceService(dev.DeviceSource(kind="serial"))
    res = svc.open()
    assert isinstance(res, Err) and res.danger_err.code == DeviceCode.NOT_FOUND
    assert svc.status == dev.DeviceStatus.ERROR


# frob:tests python/sadi/core/phases.py::open_serial
def test_serial_autodetect_picks_ftdi(monkeypatch: pytest.MonkeyPatch) -> None:
    class _P:
        def __init__(self, name: str, vid: int) -> None:
            self.name, self.vid = name, vid

    seen: list[str] = []
    monkeypatch.setattr(
        dev, "list_ports", lambda: Ok([_P("/dev/a", 1), _P("/dev/b", dev.FTDI_VID)])
    )
    monkeypatch.setattr(
        dev,
        "open_serial",
        lambda p, cfg: (seen.append(p), Err(DeviceError(code=DeviceCode.TIMEOUT)))[1],
    )
    dev.DeviceService(dev.DeviceSource(kind="serial")).open()
    assert seen == ["/dev/b"]
