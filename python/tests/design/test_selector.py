"""Tests for the advisory design selector and its benchmark."""

# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4

from __future__ import annotations

import numpy as np
from typani import Err

from sadi.design.benchmark import run_benchmark
from sadi.design.models import (
    Candidate,
    DesignPhase,
    GpState,
    Obs,
    SelectorConfig,
    SelectorError,
    TargetSpec,
)
from sadi.design.selector import select_next

CANDS = [Candidate(candidate_id=f"c{i}", x=i * 0.125) for i in range(41)]
TARGET = TargetSpec(half_width=0.05)


def _run(n: int, seed: int = 1, sd: float = 0.02):
    rng = np.random.default_rng(seed)
    obs: list[Obs] = []
    adv = None
    for _ in range(n + 1):
        adv = select_next(DesignPhase.ELASTIC, obs, CANDS, TARGET).unwrap()
        obs.append(Obs(x=adv.suggestion.x, y=2 * adv.suggestion.x + float(rng.normal(0, sd))))
    return adv, obs


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/design/selector.py::select_next
def test_cold_start_never_stops() -> None:
    """Fewer than n_min points is unreliable cold start and never says enough."""
    adv, _ = _run(1)
    assert adv.indicator.state is GpState.UNRELIABLE
    assert "cold_start" in adv.indicator.reasons
    assert adv.advisory and adv.suggestion.advisory


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/design/selector.py::select_next
def test_reaches_enough_with_patience() -> None:
    """Quiet data eventually reaches ENOUGH after patience consecutive ok prefixes."""
    adv, _ = _run(10)
    assert adv.indicator.state is GpState.ENOUGH
    assert adv.indicator.consecutive_ok >= adv.indicator.patience


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/design/selector.py::select_next
def test_deterministic() -> None:
    """Identical inputs give identical suggestions (ignoring timing)."""
    a, _ = _run(6)
    b, _ = _run(6)
    assert a.suggestion.x == b.suggestion.x
    assert a.indicator == b.indicator


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/design/selector.py::select_next
def test_under_budget() -> None:
    """A suggestion is fast and not flagged over budget."""
    adv, _ = _run(8)
    assert adv.suggestion.elapsed_ms < 200
    assert not adv.suggestion.budget_exceeded


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/design/selector.py::select_next
def test_errors() -> None:
    """Empty candidates, bad target and non-finite data are Err."""
    r = select_next(DesignPhase.ELASTIC, [], [], TARGET)
    assert isinstance(r, Err) and r.unwrap_err() is SelectorError.NoCandidates
    r = select_next(DesignPhase.ELASTIC, [], CANDS, TargetSpec(half_width=0.0))
    assert r.unwrap_err() is SelectorError.InvalidTarget
    r = select_next(DesignPhase.ELASTIC, [Obs(x=float("nan"), y=0)], CANDS, TARGET)
    assert r.unwrap_err() is SelectorError.NonFinite


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/design/selector.py::select_next
def test_yield_gp_finds_crossing() -> None:
    """The Matern52 GP locates the offset crossing near the truth (x=3.32)."""
    rng = np.random.default_rng(3)
    obs = [
        Obs(x=x, y=0.3 * x + 0.5 * max(x - 3, 0) ** 2 + float(rng.normal(0, 0.005)), u=0.005)
        for x in (0, 5, 2.5, 1, 4, 3.5, 3, 4.5)
    ]
    adv = select_next(
        DesignPhase.YIELD, obs, CANDS, TARGET, SelectorConfig(offset_response=0.05)
    ).unwrap()
    assert abs(adv.indicator.current.value - 3.32) < 0.3


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/design/selector.py::select_next
def test_yield_not_reached_explores() -> None:
    """A purely linear curve never reaches the offset, so the selector explores."""
    obs = [Obs(x=x, y=0.3 * x, u=0.005) for x in (0, 1, 2, 3, 4)]
    adv = select_next(
        DesignPhase.YIELD, obs, CANDS, TARGET, SelectorConfig(offset_response=0.05)
    ).unwrap()
    assert "yield_not_reached" in adv.indicator.reasons


# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4
# frob:tests python/sadi/design/benchmark.py::run_benchmark
def test_benchmark_beats_random_and_deterministic() -> None:
    """The GP selector is no worse than random on final half-width, and runs repeat exactly."""
    a = {r.policy: r for r in run_benchmark(trials=4)}
    assert a == {r.policy: r for r in run_benchmark(trials=4)}
    assert a["gp_selector"].mean_final_half_width <= a["random"].mean_final_half_width


# frob:ticket 01M72VM5TYFDN445BY0W9G68B1
# frob:tests python/sadi/design/selector.py::select_next
def test_elastic_cold_start_steps_up_never_zero() -> None:
    """Elastic suggestions rise from the smallest real mass and never unload or hit 0 kg."""
    cands = [Candidate(candidate_id=f"m{i}", x=3.0 * i / 24) for i in range(25)]
    obs: list[Obs] = []
    xs: list[float] = []
    for _ in range(5):
        adv = select_next(DesignPhase.ELASTIC, obs, cands, TARGET).unwrap()
        x = adv.suggestion.x
        xs.append(x)
        obs.append(Obs(x=x, y=2 * x, u=1e-6))
    assert xs[0] == cands[1].x
    assert all(b >= a for a, b in zip(xs, xs[1:], strict=False))
    assert all(x > 0.0 for x in xs)
