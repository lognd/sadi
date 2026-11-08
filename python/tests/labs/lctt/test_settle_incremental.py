"""Incremental settle scan equals the full-refit reference; streaming push stays cheap."""

# frob:ticket 01M6WYFEKW1RE3SZ1GKTPRRMMD

from __future__ import annotations

import math
import random
import time

import pytest
from typani import Ok

from sadi.labs.lctt.settle import SettleConfig, SettleScanner, detect_settle
from sadi.labs.lctt.settle_stream import StreamConfig, StreamingSettleDetector

CFG = SettleConfig(window_s=2.0, threshold=0.05, min_dwell_s=1.0, min_points=5)


def _series(kind: str, seed: int, n: int = 1500) -> tuple[list[float], list[float]]:
    """Synthetic (times, volts): noise, linear drift, or decaying creep onto a plateau."""
    rng = random.Random(seed)
    t = [1000.0 + i * 0.01 for i in range(n)]
    if kind == "noise":
        y = [rng.gauss(0.0, 0.002) for _ in t]
    elif kind == "drift":
        y = [0.2 * (a - t[0]) + rng.gauss(0.0, 0.002) for a in t]
    else:
        y = [math.exp(-(a - t[0]) / 3.0) + rng.gauss(0.0, 0.002) for a in t]
    return t, y


@pytest.mark.parametrize("kind", ["noise", "drift", "creep"])
@pytest.mark.parametrize("seed", range(5))
def test_incremental_matches_full_refit(kind: str, seed: int) -> None:
    """Same verdict, indices and slope as the exact refit, fed in uneven blocks."""
    t, y = _series(kind, seed)
    ref = detect_settle(t, y, CFG)
    assert isinstance(ref, Ok)
    scan = SettleScanner(CFG, incremental=True)
    rng = random.Random(seed)
    i = 0
    while i < len(t):
        k = rng.randint(1, 40)
        scan.feed(t[i : i + k], y[i : i + k])
        i += k
    assert scan.n_fed == len(t)
    assert scan.last_time == t[-1]
    got = scan.result()
    assert isinstance(got, Ok)
    a, b = ref.danger_ok, got.danger_ok
    assert scan.settled == a.settled
    assert (a.settled, a.settled_index, a.confirmed_index, a.reason) == (
        b.settled,
        b.settled_index,
        b.confirmed_index,
        b.reason,
    )
    assert a.window_points == b.window_points
    if a.slope is not None and b.slope is not None:
        assert b.slope.value == pytest.approx(a.slope.value, rel=1e-6, abs=1e-9)
        assert b.slope.std_unc == pytest.approx(a.slope.std_unc, rel=1e-6, abs=1e-9)


def test_streaming_push_is_fast_at_device_rate() -> None:
    """50k samples at 50 kHz pushed in 500-sample blocks finish within a generous bound."""
    det = StreamingSettleDetector(
        StreamConfig(settle=SettleConfig(window_s=0.5, threshold=1e-3, min_dwell_s=100.0))
    )
    assert isinstance(det.mark_load_change(0.0), Ok)
    rng = random.Random(1)
    t0 = time.perf_counter()
    for blk in range(100):
        ts = [(blk * 500 + j) / 50000.0 for j in range(500)]
        res = det.push(ts, [rng.gauss(0.0, 0.002) for _ in ts])
        assert isinstance(res, Ok)
    assert time.perf_counter() - t0 < 20.0
