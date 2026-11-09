"""Unit tests for the AD3 LCTT source: ADC model, segments, block packing."""

# frob:ticket 01M6Z32CP3XANNZ4ZRNGHQ8PEY
from __future__ import annotations

import numpy as np
import pytest

from sadi.bench.lctt_source import BOARD_FULL_SCALE_V, Ad3Source, AdcModel, Segment, ramp_segments
from tests.e2e.ad3_flow import make_fake


# frob:tests python/sadi/bench/lctt_source.py::AdcModel
def test_adc_quantise_round_trip_within_one_lsb() -> None:
    """Quantise then convert back stays within one LSB."""
    adc = AdcModel()
    lsb = 2 * adc.full_scale_v / 65536
    for v in (-0.9, 0.0, 0.123456, 0.9):
        assert adc.to_volts(int(adc.quantise(v))) == pytest.approx(v, abs=lsb)


# frob:ticket 01M6Z53SMZTVJW9YGWRT1ZA5MF
# frob:tests python/sadi/bench/lctt_source.py::AdcModel
def test_adc_default_matches_real_board_range() -> None:
    """The sim default is the real board's +-5.12 V range (~6413 counts/V), not 1.25 V."""
    adc = AdcModel()
    assert adc.full_scale_v == BOARD_FULL_SCALE_V == 5.12
    assert adc.quantise(0.9) == pytest.approx(38515, abs=60)


# frob:tests python/sadi/bench/lctt_source.py::ramp_segments
def test_ramp_segments_is_a_monotone_staircase() -> None:
    """Staircase has the requested step count, size and endpoints."""
    segs = ramp_segments((0.2, 0.6), (0.0, 0.4), steps=5, n_each=10)
    assert len(segs) == 5
    assert all(s.n == 10 for s in segs)
    lv = [s.lvdt_v for s in segs]
    assert lv == sorted(lv)
    assert lv[0] == pytest.approx(0.2) and lv[-1] == pytest.approx(0.6)


# frob:tests python/sadi/bench/lctt_source.py::Segment
def test_segment_rejects_empty_dwell() -> None:
    """A zero-sample segment is invalid."""
    with pytest.raises(ValueError):
        Segment(lvdt_v=0.1, n=0)


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.to_block
def test_to_block_is_packet_aligned_and_counts_messages() -> None:
    """Raw is a multiple of packet_len and msg_count continues across blocks."""
    be = make_fake()
    dev = be.open(0).danger_ok
    src = Ad3Source(be, dev)
    try:
        vols = np.zeros((100, 4))
        a = src.to_block(vols, 612)
        b = src.to_block(vols, 612)
    finally:
        src.stop()
        be.close(dev)
    assert len(a.raw) % 612 == 0 and a.n_samples == 100
    assert int(np.asarray(b.msg_count).flat[0]) > int(np.asarray(a.msg_count).flat[-1])


# frob:tests python/sadi/bench/lctt_source.py::Ad3Source.stop
def test_stop_silences_both_outputs() -> None:
    """stop() is Ok and safe to call twice."""
    be = make_fake()
    dev = be.open(0).danger_ok
    src = Ad3Source(be, dev)
    try:
        src.read(0.2, 0.1, n=50)
        assert src.stop().is_ok
        assert src.stop().is_ok
    finally:
        be.close(dev)
