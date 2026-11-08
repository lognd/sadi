"""Tests for sadi_py.acq: bounded-channel acquisition with a slow consumer."""

import time

import pytest
import sadi_py as sp
from sadi_py import acq, sim


def _stream():
    s, _ctl = sim.open("clean", 1)
    s.connect()
    s.start(sp.AdcMode.DLL_COMPATIBLE)
    return s


# frob:ticket 01M6XBHBTGXTE4TT5A9BE5FMFS
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqHandle
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqHandle.__init__
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqHandle.recv_block
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqHandle.join
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.state
def test_slow_consumer_counts_full_channel_and_never_drops() -> None:
    s = _stream()
    h = acq.AcqHandle(s, 4)
    got = 0
    end = time.monotonic() + 0.5
    while time.monotonic() < end:
        if h.recv_block(50) is not None:
            got += 1
            time.sleep(0.01)
    m = h.join()
    assert m.channel_full_waits > 0
    assert m.high_water == 4
    assert m.gaps == 0
    assert m.blocks_read == m.blocks_sent + m.blocks_lost
    assert m.blocks_lost <= 1
    assert got + m.queue_depth == m.blocks_sent
    assert m.state == "STOPPED"
    s.stop()


# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqHandle
def test_session_busy_while_acquiring() -> None:
    s = _stream()
    h = acq.AcqHandle(s)
    with pytest.raises(sp.BusyError):
        s.stop()
    h.join()
    s.stop()


# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.queue_depth
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.high_water
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.capacity
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.blocks_read
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.blocks_sent
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.gaps
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.missed_packets
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.dropped_bytes
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.channel_full_waits
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.channel_full_wait_ms
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.blocks_lost
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.read_timeouts
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.consumer_stalled
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqHandle.try_recv_block
def test_metrics_fields_and_try_recv() -> None:
    s = _stream()
    h = acq.AcqHandle(s, 8)
    deadline = time.monotonic() + 2.0
    while h.try_recv_block() is None:
        assert time.monotonic() < deadline
        time.sleep(0.001)
    m = h.join()
    for name in [
        "queue_depth",
        "high_water",
        "capacity",
        "blocks_read",
        "blocks_sent",
        "gaps",
        "missed_packets",
        "dropped_bytes",
        "channel_full_waits",
        "channel_full_wait_ms",
        "blocks_lost",
        "read_timeouts",
        "consumer_stalled",
    ]:
        assert getattr(m, name) is not None
    assert m.capacity == 8
    s.stop()


# frob:ticket 01M6XBHBTGXTE4TT5A9BE5FMFS
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqHandle.stop
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqHandle.metrics
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.error
# frob:tests crates/sadi-py/python/sadi_py/acq.pyi::AcqMetrics.state
def test_stop_is_idempotent_and_metrics_report_state() -> None:
    s = _stream()
    h = acq.AcqHandle(s, 8)
    live = h.metrics()
    assert live.capacity == 8
    assert live.error is None
    h.stop()
    h.stop()
    m = h.join()
    assert m.state == "STOPPED"
    assert m.error is None
    s.stop()
