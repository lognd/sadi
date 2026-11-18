"""Simulator benchmark: GP selector vs random vs binary-search policies on seeded scenarios."""

# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4

from __future__ import annotations

import math
from collections.abc import Callable

import numpy as np
from pydantic import BaseModel, ConfigDict

from sadi.design.models import Candidate, DesignPhase, Obs, TargetSpec
from sadi.design.selector import _van_der_corput, seed64, select_next
from sadi.logging_setup import get_logger

__all__ = ["PolicyResult", "run_benchmark"]

_log = get_logger(__name__)

TRUE_SLOPE = 2.0
NOISE_SD = 0.03
POLICIES = ("gp_selector", "random", "binary_search")


class PolicyResult(BaseModel):
    """Mean outcome of one policy over the seeded trials."""

    model_config = ConfigDict(frozen=True)

    policy: str
    mean_final_half_width: float
    mean_abs_error: float
    coverage: float


def _slope_fit(obs: list[Obs]) -> tuple[float, float]:
    x = np.array([o.x for o in obs])
    y = np.array([o.y for o in obs])
    b, a = np.polyfit(x, y, 1)
    res = y - (a + b * x)
    s = math.sqrt(float(res @ res) / (len(obs) - 2))
    half = 2.0 * s / math.sqrt(float(np.sum((x - x.mean()) ** 2)))
    return float(b), half


def _pick(
    policy: str, cands: list[Candidate], obs: list[Obs], seed: int, rng: np.random.Generator
) -> Candidate:
    n = len(obs)
    if policy == "random":
        return cands[int(rng.integers(len(cands)))]
    if policy == "binary_search" or n < 3:
        want = (0.0, 1.0)[n] if n < 2 else _van_der_corput(n - 1)
        x = cands[0].x + (cands[-1].x - cands[0].x) * want
        return min(cands, key=lambda c: abs(c.x - x))
    adv = select_next(
        DesignPhase.ELASTIC, obs, cands, TargetSpec(half_width=0.05), session_id=str(seed)
    ).unwrap()
    return next(c for c in cands if c.candidate_id == adv.suggestion.candidate_id)  # type: ignore[union-attr]


def run_benchmark(
    trials: int = 5, n_points: int = 8, seed: int = 0, truth: Callable[[float], float] | None = None
) -> list[PolicyResult]:
    """Run each policy for `n_points` observations on `trials` seeded trials; deterministic."""
    f = truth or (lambda x: TRUE_SLOPE * x)
    cands = [Candidate(candidate_id=f"c{i}", x=i * 0.125) for i in range(41)]
    out: list[PolicyResult] = []
    for policy in POLICIES:
        halves, errs, covered = [], [], 0
        for t in range(trials):
            s = seed64("bench", DesignPhase.ELASTIC, seed * 1000 + t)
            rng = np.random.default_rng(s)
            obs: list[Obs] = []
            for _ in range(n_points):
                c = _pick(policy, cands, obs, s, rng)
                obs.append(Obs(x=c.x, y=f(c.x) + float(rng.normal(0, NOISE_SD)), u=NOISE_SD))
            b, h = _slope_fit(obs)
            halves.append(h)
            errs.append(abs(b - TRUE_SLOPE))
            covered += abs(b - TRUE_SLOPE) <= h
        res = PolicyResult(
            policy=policy,
            mean_final_half_width=float(np.mean(halves)),
            mean_abs_error=float(np.mean(errs)),
            coverage=covered / trials,
        )
        _log.info(
            "benchmark %s hw=%.4g err=%.4g cov=%.2f",
            policy,
            res.mean_final_half_width,
            res.mean_abs_error,
            res.coverage,
        )
        out.append(res)
    return out
