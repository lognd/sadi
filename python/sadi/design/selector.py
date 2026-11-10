"""Sequential-design selector: Bayesian linear phases plus a Matern52 GP yield phase (advisory)."""

# frob:ticket 01M72PGN2KAMZP8EPHDPV143B4

from __future__ import annotations

import hashlib
import math
import time
from collections.abc import Callable, Sequence

import numpy as np
from typani import Err, Ok, Result

from sadi.design.models import (
    AltCandidate,
    Candidate,
    ConfidenceIndicator,
    CurrentFit,
    DesignAdvice,
    DesignPhase,
    GpState,
    NextSuggestion,
    Obs,
    SelectorConfig,
    SelectorError,
    TargetSpec,
)
from sadi.logging_setup import get_logger
from sadi.uncertainty.coverage import t95

__all__ = ["seed64", "select_next"]

_log = get_logger(__name__)

#: Weak prior precision on (intercept, slope) in normalised units.
PRIOR_PRECISION = 1e-6
#: Number of runner-up candidates reported.
N_ALTERNATIVES = 3
#: Standardised residual above which the last point departs from the linear model.
DEPARTURE_Z = 4.0
#: Floor on the noise variance (relative to response variance) so fits never divide by zero.
NOISE_FLOOR_REL = 1e-8
#: Length-scale / amplitude grids for the GP marginal-likelihood choice (deterministic).
_LS_FRACS = (0.1, 0.2, 0.4, 0.8)
_SF_FRACS = (0.5, 1.0, 2.0)


def seed64(session_id: str, phase: DesignPhase, n: int) -> int:
    """Return a stable 64-bit seed from (session, phase, n); the selector itself uses no RNG."""
    h = hashlib.blake2b(f"{session_id}|{phase.value}|{n}".encode(), digest_size=8)
    return int.from_bytes(h.digest(), "big")


def _t(dof: float) -> float:
    r = t95(max(dof, 1.0))
    return r.unwrap() if isinstance(r, Ok) else 1.96


class _Fit:
    """Posterior summary of one phase model: the target estimate, its half-width and gain fn."""

    def __init__(self, value: float, half: float, dof: float, gain: Callable[[float], float]):
        self.value, self.half, self.dof, self.gain = value, half, dof, gain


# ---------------------------------------------------------------- linear phases
def _fit_linear(obs: Sequence[Obs], lo: float, hi: float) -> _Fit | None:
    """Bayesian line fit; target is the slope. Returns None when fewer than 3 points."""
    n = len(obs)
    if n < 3:
        return None
    mid, half_rng = (lo + hi) / 2.0, max((hi - lo) / 2.0, 1e-12)
    xn = np.array([(o.x - mid) / half_rng for o in obs])
    y = np.array([o.y for o in obs])
    phi = np.column_stack([np.ones(n), xn])
    prec = phi.T @ phi + PRIOR_PRECISION * np.eye(2)
    try:
        cov0 = np.linalg.inv(prec)
    except np.linalg.LinAlgError:
        return None
    beta = cov0 @ (phi.T @ y)
    dof = n - 2
    rss = float(np.sum((y - phi @ beta) ** 2))
    mean_u2 = float(np.mean([o.u**2 for o in obs]))
    floor = NOISE_FLOOR_REL * max(float(np.var(y)), 1e-300)
    s2 = max(rss / dof, mean_u2, floor)
    cov = s2 * cov0
    slope = float(beta[1] / half_rng)
    half = _t(dof) * math.sqrt(cov[1, 1]) / half_rng
    t_next = _t(dof + 1)

    def gain(x: float) -> float:
        f = np.array([1.0, (x - mid) / half_rng])
        pf = cov @ f
        v1 = cov[1, 1] - pf[1] ** 2 / (s2 + float(f @ pf))
        return half - t_next * math.sqrt(max(v1, 0.0)) / half_rng

    fit = _Fit(slope, half, dof, gain)
    fit.resid = y - phi @ beta  # type: ignore[attr-defined]
    fit.s2 = s2  # type: ignore[attr-defined]
    return fit


def _departs(obs: Sequence[Obs], lo: float, hi: float) -> bool:
    """True when the newest point is > DEPARTURE_Z predictive sd from the line of the others."""
    if len(obs) < 6:
        return False
    prev, last = obs[:-1], obs[-1]
    mid, hr = (lo + hi) / 2.0, max((hi - lo) / 2.0, 1e-12)
    xn = np.array([(o.x - mid) / hr for o in prev])
    y = np.array([o.y for o in prev])
    phi = np.column_stack([np.ones(len(prev)), xn])
    try:
        cov0 = np.linalg.inv(phi.T @ phi + PRIOR_PRECISION * np.eye(2))
    except np.linalg.LinAlgError:
        return False
    beta = cov0 @ (phi.T @ y)
    rss = float(np.sum((y - phi @ beta) ** 2))
    s2 = max(rss / (len(prev) - 2), last.u**2, NOISE_FLOOR_REL * max(float(np.var(y)), 1e-300))
    f = np.array([1.0, (last.x - mid) / hr])
    sd = math.sqrt(s2 * (1.0 + float(f @ cov0 @ f)))
    return abs(last.y - float(f @ beta)) / sd > DEPARTURE_Z


# ---------------------------------------------------------------- yield GP
def _matern52(a: np.ndarray, b: np.ndarray, sf: float, ell: float) -> np.ndarray:
    r = np.abs(a[:, None] - b[None, :]) * math.sqrt(5.0) / ell
    return sf**2 * (1.0 + r + r**2 / 3.0) * np.exp(-r)


def _fit_yield(obs: Sequence[Obs], lo: float, hi: float, cfg: SelectorConfig) -> _Fit | str:
    """GP on departure from the elastic line; target is the 0.2 % offset crossing x*.

    Returns a reason string when the crossing cannot be located.
    """
    if cfg.offset_response is None:
        return "no_offset"
    pts = sorted(obs[-cfg.max_gp_points :], key=lambda o: o.x)
    n = len(pts)
    x = np.array([o.x for o in pts])
    y = np.array([o.y for o in pts])
    k = max(3, n // 2)
    slope, icpt = np.polyfit(x[:k], y[:k], 1)
    r = y - (icpt + slope * x)
    span = max(hi - lo, 1e-12)
    noise = np.array([o.u**2 for o in pts]) + NOISE_FLOOR_REL * max(float(np.var(y)), 1e-300)
    sd_r = max(float(np.std(r)), 1e-12)
    best: tuple[float, float, float, np.ndarray] | None = None
    for ls in _LS_FRACS:
        for sf in _SF_FRACS:
            ell, amp = ls * span, sf * sd_r * 3.0
            kmat = _matern52(x, x, amp, ell) + np.diag(noise + (1e-3 * sd_r) ** 2)
            try:
                chol = np.linalg.cholesky(kmat)
            except np.linalg.LinAlgError:
                continue
            alpha = np.linalg.solve(chol.T, np.linalg.solve(chol, r))
            lml = -0.5 * float(r @ alpha) - float(np.sum(np.log(np.diag(chol))))
            if best is None or lml > best[0] + 1e-12:
                best = (lml, ell, amp, chol)
    if best is None:
        return "singular"
    _, ell, amp, chol = best
    nz = noise + (1e-3 * sd_r) ** 2

    def post(xs: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        ks = _matern52(xs, x, amp, ell)
        v = np.linalg.solve(chol, ks.T)
        mean = ks @ np.linalg.solve(chol.T, np.linalg.solve(chol, r))
        var = amp**2 - np.sum(v**2, axis=0)
        return mean, np.maximum(var, 0.0)

    grid = np.linspace(lo, hi, 257)
    mean, _ = post(grid)
    above = np.nonzero(mean >= cfg.offset_response)[0]
    if above.size == 0:
        return "yield_not_reached"
    i = int(above[0])
    if i == 0:
        return "yield_not_reached"
    # linear interpolation of the crossing
    x0, x1, m0, m1 = grid[i - 1], grid[i], mean[i - 1], mean[i]
    xs = float(x0 + (cfg.offset_response - m0) * (x1 - x0) / (m1 - m0)) if m1 != m0 else float(x1)
    h = span / 256.0
    mp, _ = post(np.array([xs - h, xs + h]))
    deriv = float((mp[1] - mp[0]) / (2 * h))
    if abs(deriv) < 1e-12:
        return "yield_not_reached"
    pa = np.array([xs])
    _, var_s = post(pa)
    dof = max(n - 3, 1)
    t = _t(dof)
    half = t * math.sqrt(float(var_s[0])) / abs(deriv)
    ks_star = _matern52(pa, x, amp, ell)[0]
    w_star = np.linalg.solve(chol, ks_star)

    def gain(xc: float) -> float:
        c = np.array([xc])
        kc = _matern52(c, x, amp, ell)[0]
        wc = np.linalg.solve(chol, kc)
        cov_sc = float(_matern52(pa, c, amp, ell)[0, 0] - w_star @ wc)
        var_c = max(amp**2 - float(wc @ wc), 0.0)
        v1 = float(var_s[0]) - cov_sc**2 / (var_c + float(np.mean(nz)))
        return half - _t(dof + 1) * math.sqrt(max(v1, 0.0)) / abs(deriv)

    return _Fit(xs, half, dof, gain)


# ---------------------------------------------------------------- driver
def _fit(
    phase: DesignPhase, obs: Sequence[Obs], lo: float, hi: float, cfg: SelectorConfig
) -> _Fit | str:
    if phase is DesignPhase.YIELD:
        if len(obs) < cfg.n_min_yield:
            return "cold_start"
        return _fit_yield(obs, lo, hi, cfg)
    if len(obs) < cfg.n_min_linear:
        return "cold_start"
    f = _fit_linear(obs, lo, hi)
    return f if f is not None else "singular"


def _van_der_corput(k: int) -> float:
    q, denom, n = 0.0, 1.0, k
    while n:
        n, rem = divmod(n, 2)
        denom *= 2.0
        q += rem / denom
    return q


def _cold_pick(cands: Sequence[Candidate], n: int, lo: float, hi: float) -> Candidate:
    """Space-filling pick: extremes first, then bisection points, snapped to a candidate."""
    if n == 0:
        want = lo
    elif n == 1:
        want = hi
    else:
        want = lo + (hi - lo) * _van_der_corput(n - 1)
    return min(cands, key=lambda c: (abs(c.x - want), c.candidate_id))


def _need(target: TargetSpec, value: float | None) -> float | None:
    if target.relative:
        return None if value is None else target.half_width * abs(value)
    return target.half_width


def select_next(  # noqa: PLR0913
    phase: DesignPhase,
    obs: Sequence[Obs],
    candidates: Sequence[Candidate],
    target: TargetSpec,
    config: SelectorConfig | None = None,
    *,
    session_id: str = "",
    job_version: int = 0,
    unit: str = "",
    clock: Callable[[], float] = time.perf_counter,
) -> Result[DesignAdvice, SelectorError]:
    """Advise the next candidate and whether confidence is enough (deterministic, advisory)."""
    t0 = clock()
    cfg = config or SelectorConfig()
    if not candidates:
        return Err(SelectorError.NoCandidates)
    if not (math.isfinite(target.half_width) and target.half_width > 0):
        return Err(SelectorError.InvalidTarget)
    if any(not (math.isfinite(o.x) and math.isfinite(o.y) and math.isfinite(o.u)) for o in obs):
        return Err(SelectorError.NonFinite)
    if any(not math.isfinite(c.x) for c in candidates):
        return Err(SelectorError.NonFinite)
    cands = sorted(candidates, key=lambda c: (c.x, c.candidate_id))
    lo, hi = cands[0].x, cands[-1].x
    n = len(obs)
    n_min = cfg.n_min_yield if phase is DesignPhase.YIELD else cfg.n_min_linear

    fit = _fit(phase, obs, lo, hi, cfg)
    reasons: list[str] = []
    state = GpState.COLLECTING
    cur = CurrentFit(half_width=None, value=None, dof=float(max(n - 2, 0)))
    ratio: float | None = None
    consecutive = 0
    gains: list[tuple[float, Candidate]] = []

    if isinstance(fit, str):
        reasons.append(fit)
        state = GpState.UNRELIABLE if fit in {"cold_start", "singular"} else GpState.COLLECTING
        if fit == "cold_start":
            pick = _cold_pick(cands, n, lo, hi)
            gains = [(0.0, pick)] + [(0.0, c) for c in cands if c is not pick][:N_ALTERNATIVES]
        elif fit == "yield_not_reached":
            # explore upward: highest-load candidates first (nothing is known beyond the data)
            above = [c for c in cands if c.x > max((o.x for o in obs), default=lo)] or cands
            pick = above[len(above) // 2]
            gains = [(0.0, pick)] + [(0.0, c) for c in above if c is not pick][:N_ALTERNATIVES]
        else:
            gains = [(0.0, c) for c in cands[: N_ALTERNATIVES + 1]]
    else:
        cur = CurrentFit(half_width=fit.half, value=fit.value, dof=float(fit.dof))
        need = _need(target, fit.value)
        ratio = None if not need else fit.half / need
        # stop rule over the last `patience` prefixes
        for k in range(cfg.patience):
            pre = obs[: n - k]
            if len(pre) < n_min:
                break
            pf = fit if k == 0 else _fit(phase, pre, lo, hi, cfg)
            if isinstance(pf, str):
                break
            pneed = _need(target, pf.value)
            if pneed and pf.half <= cfg.margin * pneed:
                consecutive += 1
            else:
                break
        gains = sorted(
            ((fit.gain(c.x), c) for c in cands), key=lambda g: (-g[0], g[1].x, g[1].candidate_id)
        )
        best_gain = gains[0][0]
        if phase is not DesignPhase.YIELD and _departs(obs, lo, hi):
            state = GpState.UNRELIABLE
            reasons.append("departure_from_linear")
        elif consecutive >= cfg.patience:
            state = GpState.ENOUGH
        elif best_gain < cfg.eps * fit.half:
            state = GpState.DIMINISHING
            reasons.append("diminishing_returns")
        else:
            state = GpState.COLLECTING

    top = gains[0]
    elapsed = (clock() - t0) * 1000.0
    over = elapsed > cfg.budget_ms
    exp_half = None if isinstance(fit, str) else max(fit.half - top[0], 0.0)
    alts = tuple(
        AltCandidate(candidate_id=c.candidate_id, x=c.x, expected_gain=g)
        for g, c in gains[1 : 1 + N_ALTERNATIVES]
    )
    sug = NextSuggestion(
        phase=phase,
        job_version=job_version,
        candidate_id=top[1].candidate_id,
        x=top[1].x,
        unit=unit,
        expected_gain=top[0],
        expected_half_width=exp_half,
        alternatives=alts,
        criterion=cfg.criterion,
        elapsed_ms=elapsed,
        budget_exceeded=over,
        why=_why(state, reasons, top[0]),
    )
    ind = ConfidenceIndicator(
        phase=phase,
        job_version=job_version,
        n=n,
        target=target,
        current=cur,
        ratio=ratio,
        state=state,
        consecutive_ok=consecutive,
        patience=cfg.patience,
        reasons=tuple(reasons),
    )
    _log.debug(
        "design %s n=%d state=%s x=%.4g gain=%.3g ms=%.1f",
        phase.value,
        n,
        state.value,
        sug.x,
        sug.expected_gain,
        elapsed,
    )
    return Ok(DesignAdvice(suggestion=sug, indicator=ind))


def _why(state: GpState, reasons: Sequence[str], gain: float) -> str:
    """One plain sentence explaining the pick, for the student."""
    if "cold_start" in reasons:
        return "Too few points to model yet, so this spreads your points across the range."
    if "yield_not_reached" in reasons:
        return "The curve has not bent over yet, so try a heavier load to find where it yields."
    if "departure_from_linear" in reasons:
        return "The last point is off the straight line; recheck it before adding more."
    if state is GpState.ENOUGH:
        return "You already have enough data; another point barely helps."
    if gain > 0:
        return "This load should tighten the result the most."
    return "This load is the best remaining choice."
