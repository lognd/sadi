"""Tests for sadi.core.phases: typed phase classes, spent-object bugs, error conversion."""

# frob:ticket 01M6W7R2NWFTQBK7FRWGX511CP

from __future__ import annotations

import pytest
from typani import Err, Ok

sp = pytest.importorskip("sadi_py", reason="sadi_py extension not built (maturin develop)")

from sadi.core import phases  # noqa: E402
from sadi.core.errors import DeviceCode  # noqa: E402


def _connected() -> phases.Connected:
    disc = phases.open_sim("clean", 1).unwrap()
    return disc.connect().unwrap()


# frob:tests python/sadi/core/phases.py::Disconnected.connect
# frob:tests python/sadi/core/phases.py::Connected.start
# frob:tests python/sadi/core/phases.py::Streaming.read_block
# frob:tests python/sadi/core/phases.py::Streaming.stop
# frob:tests python/sadi/core/phases.py::Stopped.restart
# frob:tests python/sadi/core/phases.py::Stopped.close
# frob:tests python/sadi/core/phases.py::open_sim
def test_full_lifecycle_against_simulator() -> None:
    conn = _connected()
    streaming = conn.start(sp.AdcMode.DLL_COMPATIBLE).unwrap()
    block = streaming.read_block().unwrap()
    assert block.n_samples > 0
    stopped, tail = streaming.stop().unwrap()
    assert isinstance(tail.raw, bytes)
    conn2 = stopped.restart().unwrap()
    assert isinstance(conn2, phases.Connected)
    assert conn2.close() == Ok(None)


# frob:tests python/sadi/core/phases.py::_Phase.spent
# frob:tests python/sadi/core/phases.py::_Phase._live
# frob:tests python/sadi/core/phases.py::_Phase._spend
# frob:tests python/sadi/core/devfacade.py::SpentPhaseError
def test_transition_spends_previous_object() -> None:
    conn = _connected()
    streaming = conn.start(sp.AdcMode.DLL_COMPATIBLE).unwrap()
    assert conn.spent
    with pytest.raises(phases.SpentPhaseError):
        conn.query()
    with pytest.raises(phases.SpentPhaseError):
        conn.start(sp.AdcMode.DLL_COMPATIBLE)
    assert not streaming.spent
    streaming.stop().unwrap()
    with pytest.raises(phases.SpentPhaseError):
        streaming.read_block()


# frob:tests python/sadi/core/phases.py::Connected.query
# frob:tests python/sadi/core/phases.py::Connected.disconnect
# frob:tests python/sadi/core/phases.py::Connected.close
# frob:tests python/sadi/core/phases.py::Disconnected.close
# frob:tests python/sadi/core/phases.py::_Phase.description
def test_query_disconnect_close() -> None:
    conn = _connected()
    assert conn.description
    assert conn.query().unwrap().state_byte >= 0
    disc = conn.disconnect().unwrap()
    assert isinstance(disc, phases.Disconnected)
    assert disc.close() == Ok(None)
    assert disc.spent


# frob:tests python/sadi/core/devfacade.py::guard
# frob:tests python/sadi/core/devfacade.py::to_device_error
def test_bad_scenario_becomes_err_with_hint() -> None:
    res = phases.open_sim("no-such-scenario")
    assert isinstance(res, Err)
    err = res.danger_err
    assert err.code == DeviceCode.NOT_FOUND
    assert err.hint


class _Fake(sp.SadiError):
    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind
        self.detail = f"fake {kind}"


@pytest.mark.parametrize(
    ("kind", "code"),
    [
        ("transport_timeout", DeviceCode.TIMEOUT),
        ("read_timeout", DeviceCode.TIMEOUT),
        ("transport_closed", DeviceCode.DISCONNECTED),
        ("codec", DeviceCode.PROTOCOL),
        ("scenario", DeviceCode.NOT_FOUND),
        ("never-heard-of-it", DeviceCode.PROTOCOL),
    ],
)
# frob:tests python/sadi/core/devfacade.py::to_device_error
def test_kind_mapping(kind: str, code: DeviceCode) -> None:
    assert phases.to_device_error(_Fake(kind)).code == code


# frob:tests python/sadi/core/devfacade.py::guard
def test_guard_reraises_programmer_bugs() -> None:
    def boom() -> None:
        raise _Fake("phase")

    with pytest.raises(sp.SadiError):
        phases.guard("x", boom)
    res = phases.guard("x", lambda: (_ for _ in ()).throw(_Fake("transport_io")))
    assert isinstance(res, Err)


# frob:tests python/sadi/core/phases.py::list_ports
def test_list_ports_is_ok() -> None:
    assert phases.list_ports().is_ok
