"""Hardware-marked LCTT stimulus checks on a real AD3; auto-skip without AD3 and SADI board."""

# frob:ticket 01M6Z32CP3XANNZ4ZRNGHQ8PEY
from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from sadi.bench.ad3 import load_backend
from sadi.bench.inject import SADI_PINS, capture, inject_dc, inject_lvdt
from sadi.bench.lctt_source import MAX_SAFE_V, Ad3Source, Segment
from sadi.bench.sadi_readback import board_adc_model, read_board
from sadi.logging_setup import get_logger

_log = get_logger("tests.bench.lctt_ad3_hw")

pytestmark = pytest.mark.ad3_hw

# SADI_PORT names the board; levels are read back over the serial facade, the AD3 scope
# (index 0 = Scope Channel 1) only monitors the 3V3 supply.
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


# frob:ticket 01M6Z3FR48WS686Q8Z52SQ2BN8
def _inject(src: Ad3Source, lvdt_v: float, load_v: float) -> None:
    """Hold DC levels on W1 (lvdt) and W2 (load); stays applied until `src.stop()`."""
    for res in (
        inject_lvdt(src.be, src.dev, src.pins, 0.0, 1000.0, offset_v=lvdt_v),
        inject_dc(src.be, src.dev, src.pins, load_v),
    ):
        assert res.is_ok, res


# frob:tests python/sadi/bench/sadi_readback.py::read_board
def test_hw_dc_levels_read_back_on_board(hw_source: Ad3Source, tmp_path: Path) -> None:
    """W1 levels up to 1 V appear on SADI ACH0 within 2 percent, ACH1 floating stays ~0."""
    port = os.environ[SADI_PORT_ENV]
    model = board_adc_model()
    for level in (0.2, 0.5, MAX_SAFE_V * 0.9):
        _inject(hw_source, level, 0.0)
        got = read_board(port)
        assert got.is_ok, got
        r = got.danger_ok
        tol_v = 0.02 * max(level, 0.1)
        _log.info("board ACH0 level=%.3f volts=%.5f code=%.1f", level, r.volts[0], r.codes[0])
        assert r.volts[0] == pytest.approx(level, abs=tol_v)
        assert r.codes[0] == pytest.approx(model.quantise(level), abs=tol_v / 2 * 65535 / 5.12)
        assert abs(r.volts[1]) < 0.02  # ACH1 is floating
    assert not list(tmp_path.iterdir())  # never writes outside tmp, never touches data files


# frob:tests python/sadi/bench/sadi_readback.py::read_board
def test_hw_load_route_reads_negative_on_board(hw_source: Ad3Source) -> None:
    """W2 -> ACH2 is wired with negative polarity: +0.5 V applied reads -0.5 V on the board."""
    _inject(hw_source, 0.0, 0.5)
    got = read_board(os.environ[SADI_PORT_ENV])
    assert got.is_ok, got
    r = got.danger_ok
    _log.info("board ACH2 applied=0.5 volts=%.5f code=%.1f", r.volts[2], r.codes[2])
    assert r.volts[2] == pytest.approx(-0.5, abs=0.02 * 0.5)
    assert abs(r.volts[0]) < 0.02  # lvdt route idle


# frob:tests python/sadi/bench/inject.py::capture
def test_hw_supply_monitor_reads_3v3(hw_source: Ad3Source) -> None:
    """AD3 Scope Channel 1 (index 0) sits on SADI GND/+3V3 and reads the 3.3 V supply."""
    scope = SADI_PINS.supply_scope_channel
    assert scope is not None
    got = capture(hw_source.be, hw_source.dev, scope, 10_000.0, 500)
    assert got.is_ok, got
    mean_v = sum(got.danger_ok) / len(got.danger_ok)
    _log.info("supply monitor scope idx %d mean %.4f V", scope, mean_v)
    assert mean_v == pytest.approx(3.3, abs=0.15)


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.stream
def test_hw_staircase_streams_without_error(hw_source: Ad3Source) -> None:
    """A small ramp staircase streams from the AD3 as a Result::Ok block."""
    seg = Segment(lvdt_v=0.3, load_v=0.1, n=500)
    assert hw_source.stream([seg]).is_ok
