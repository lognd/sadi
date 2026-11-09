"""Offline checks for the SADI board read-back helper (hardware runs live in test_lctt_ad3_hw)."""

# frob:ticket 01M6Z3FR48WS686Q8Z52SQ2BN8
from __future__ import annotations

import pytest
from typani import Err

from sadi.bench.sadi_readback import BOARD_FULL_SCALE_V, board_adc_model, read_board


# frob:tests python/sadi/bench/sadi_readback.py::board_adc_model
def test_board_model_uses_5v12_range_and_measured_scale() -> None:
    """0.9 V maps to code ~38515, the count measured on the real board (6413 counts/V)."""
    m = board_adc_model()
    assert m.full_scale_v == BOARD_FULL_SCALE_V == 5.12
    assert m.quantise(0.9) == pytest.approx(38515, abs=60)


# frob:tests python/sadi/bench/sadi_readback.py::read_board
def test_read_board_missing_port_is_err() -> None:
    """An unusable port yields Err, never an exception."""
    assert isinstance(read_board("/dev/does-not-exist"), Err)
