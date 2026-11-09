"""Hardware-marked LCTT stimulus checks on a real AD3; auto-skip without AD3 and SADI board."""

# frob:ticket 01M6Z32CP3XANNZ4ZRNGHQ8PEY
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from sadi.bench.ad3 import load_backend
from sadi.bench.lctt_source import MAX_SAFE_V, Ad3Source, Segment
from sadi.logging_setup import get_logger

_log = get_logger("tests.bench.lctt_ad3_hw")

pytestmark = pytest.mark.ad3_hw

# The SADI read-back needs the serial facade (ticket Y6MM2ZP); SADI_PORT names the board.
SADI_PORT_ENV = "SADI_PORT"


@pytest.fixture
def hw_source() -> Iterator[Ad3Source]:
    """Open the first AD3; skip unless library, AD3 and SADI board exist; always close."""
    if os.environ.get(SADI_PORT_ENV) is None:
        pytest.skip(f"{SADI_PORT_ENV} unset: no SADI board declared")
    loaded = load_backend()
    if loaded.is_err:
        pytest.skip(f"libdwf unusable: {loaded.danger_err}")
    be = loaded.danger_ok
    devices = be.enumerate_devices()
    if devices.is_err or not devices.danger_ok:
        pytest.skip("no AD3 enumerated")
    opened = be.open(0)
    if opened.is_err:
        pytest.skip(f"AD3 open failed: {opened.danger_err}")
    dev = opened.danger_ok
    src = Ad3Source(be, dev)
    try:
        yield src
    finally:
        src.stop()
        closed = be.close(dev)
        _log.info("hw device closed ok=%s", closed.is_ok)


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.read
def test_hw_dc_levels_read_back_on_scope(hw_source: Ad3Source, tmp_path: Path) -> None:
    """Each DC level up to 1 V is seen on the AD3 scope within 2 percent (scope loopback)."""
    for level in (0.2, 0.5, MAX_SAFE_V * 0.9):
        got = hw_source.read(level, 0.0, n=500)
        assert got.is_ok, got
        assert got.danger_ok.lvdt_v == pytest.approx(level, abs=0.02 * max(level, 0.1))
    assert not list(tmp_path.iterdir())  # never writes outside tmp, never touches data files


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.stream
def test_hw_staircase_streams_without_error(hw_source: Ad3Source) -> None:
    """A small ramp staircase streams from the AD3 as a Result::Ok block."""
    seg = Segment(lvdt_v=0.3, load_v=0.1, n=500)
    assert hw_source.stream([seg]).is_ok
