"""GP/c-optimal load selector for the LCTT guided run (advisory: the user picks the load)."""

# frob:ticket 01M71KCTETKE1AE0GZ35MQ11EV

from __future__ import annotations

import math
from enum import StrEnum

import numpy as np
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.core.results import ResultSet
from sadi.labs.lctt.guidance import (
    EvenScheduleSuggester,
    GuidanceError,
    LoadRange,
    LoadSuggestion,
    Phase,
    mass_guidance_text,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

#: Candidate loads per suggestion (inclusive grid over the safe range).
N_CANDIDATES = 41
#: Two-sided 95 % normal quantile used for half-widths.
Z95 = 1.96
#: Fewest observations before the model (rather than the cold-start schedule) is used.
MIN_MODEL_POINTS = 3
#: Fewest observations before "diminishing" / "unreliable" may be reported.
MIN_JUDGE_POINTS = 5
#: Relative gain below which further points are reported as diminishing.
DIMINISHING_FRACTION = 0.02
#: Weak ridge prior precision on (intercept, slope) in normalised load units.
PRIOR_PRECISION = 1e-6
#: Default GP length scale as a fraction of the load range.
DEFAULT_LENGTH_SCALE = 0.25
_NOISE_FLOOR = 1e-12


class GpState(StrEnum):
    """Advisory model state shown in the UI; never gates anything."""

    COLLECTING = "collecting"
    ENOUGH = "enough"
    DIMINISHING = "diminishing"
    UNRELIABLE = "unreliable"


class Kernel(StrEnum):
    """Stationary kernels available for the plastic-phase GP."""

    MATERN52 = "matern52"
    RBF = "rbf"


class Observation(BaseModel):
    """One accepted point: total load (kg) and the measured response (e.g. strain)."""

    model_config = ConfigDict(frozen=True)

    load_kg: float
    response: float


class Scored(BaseModel):
    """Result of scoring the candidate grid."""

    model_config = ConfigDict(frozen=True)

    load_kg: float
    gain: float
    half_width: float
    alternatives: tuple[float, ...]
    state: GpState


def _vdc(j: int) -> float:
    """Van der Corput base-2 value of j >= 1: 1/2, 1/4, 3/4, 1/8, 5/8, ..."""
    out, denom = 0.0, 1.0
    while j > 0:
        denom *= 2.0
        out += (j & 1) / denom
        j >>= 1
    return out


def cold_start_load(k: int, load_range: LoadRange) -> float:
    """Load for point index k with no model yet: minimum, maximum, then bisection midpoints."""
    span = load_range.max_kg - load_range.min_kg
    if k <= 0:
        return load_range.min_kg
    if k == 1:
        return load_range.max_kg
    return load_range.min_kg + span * _vdc(k - 1)


def _kernel(a: np.ndarray, b: np.ndarray, kind: Kernel, length: float) -> np.ndarray:
    """Unit-variance kernel matrix between 1-D point sets."""
    d = np.abs(a[:, None] - b[None, :]) / length
    if kind is Kernel.RBF:
        return np.exp(-0.5 * d * d)
    s5 = math.sqrt(5.0) * d
    return (1.0 + s5 + (5.0 / 3.0) * d * d) * np.exp(-s5)


def _rank(score: np.ndarray) -> list[int]:
    """Indices best-first; ties (to 10 digits) resolve to the lowest index."""
    return [int(i) for i in np.argsort(-np.round(score, 10), kind="stable")]


class GpLoadSuggester:
    """LoadSuggester: c-optimal for the elastic slope, GP information gain for the plastic curve."""

    def __init__(  # noqa: PLR0913
        self,
        observations: tuple[Observation, ...] = (),
        noise_var: float = 1e-4,
        kernel: Kernel = Kernel.MATERN52,
        length_scale: float = DEFAULT_LENGTH_SCALE,
        fallback: EvenScheduleSuggester | None = None,
    ) -> None:
        """Hold the observed points, default noise variance, kernel and the even fallback."""
        self._obs: list[Observation] = list(observations)
        self._noise = noise_var
        self._kernel = kernel
        self._length = length_scale
        self._fallback = fallback or EvenScheduleSuggester()
        self.last: Scored | None = None

    def observe(self, load_kg: float, response: float) -> Result[int, GuidanceError]:
        """Record an accepted point; returns the new count, rejects non-finite values."""
        if not (math.isfinite(load_kg) and math.isfinite(response)):
            _log.warning("observe: rejected (%r, %r)", load_kg, response)
            return Err(GuidanceError.SuggesterFailed)
        self._obs.append(Observation(load_kg=load_kg, response=response))
        _log.debug("observe: %d points", len(self._obs))
        return Ok(len(self._obs))

    def reset(self) -> None:
        """Forget all observations (new phase or new specimen)."""
        self._obs.clear()
        self.last = None

    def suggest(
        self, phase: Phase, results: ResultSet, load_range: LoadRange
    ) -> Result[LoadSuggestion, GuidanceError]:
        """Propose the next load; falls back to the even schedule if the model fails."""
        got = self._model_suggest(phase, results, load_range)
        if isinstance(got, Err):
            _log.warning("gp suggester failed (%s); using even schedule", got.danger_err)
            self.last = None
            fb = self._fallback.suggest(phase, results, load_range)
            if isinstance(fb, Err):
                return fb
            return Ok(fb.danger_ok.model_copy(update={"gp_state": GpState.UNRELIABLE.value}))
        return got

    def _model_suggest(
        self, phase: Phase, results: ResultSet, load_range: LoadRange
    ) -> Result[LoadSuggestion, GuidanceError]:
        """Cold start, elastic c-optimal or plastic GP choice, all clipped to the range."""
        n = len(self._obs)
        if any(not (math.isfinite(o.load_kg) and math.isfinite(o.response)) for o in self._obs):
            return Err(GuidanceError.SuggesterFailed)
        if n < MIN_MODEL_POINTS:
            k = n if n else results.n_points
            kg = cold_start_load(k, load_range)
            self.last = None
            _log.debug("cold start k=%d -> %.4f kg", k, kg)
            return Ok(
                LoadSuggestion(
                    load_kg=kg,
                    text=mass_guidance_text(kg),
                    gp_state=GpState.COLLECTING.value,
                )
            )
        grid = np.linspace(load_range.min_kg, load_range.max_kg, N_CANDIDATES)
        span = load_range.max_kg - load_range.min_kg
        x = (np.array([o.load_kg for o in self._obs]) - load_range.min_kg) / span
        y = np.array([o.response for o in self._obs])
        cand = (grid - load_range.min_kg) / span
        try:
            if phase is Phase.ELASTIC:
                score, now, after, noise = self._c_optimal(x, y, cand, span)
            else:
                score, now, after, noise = self._gp(x, y, cand)
        except np.linalg.LinAlgError:
            return Err(GuidanceError.SuggesterFailed)
        if not np.all(np.isfinite(score)):
            return Err(GuidanceError.SuggesterFailed)
        order = _rank(score)
        best = order[0]
        kg = float(min(load_range.max_kg, max(load_range.min_kg, grid[best])))
        gain = max(0.0, now - after[best])
        state = self._state(n, now, gain, noise, y)
        alts = tuple(float(grid[i]) for i in order[:3])
        self.last = Scored(
            load_kg=kg, gain=gain, half_width=float(after[best]), alternatives=alts, state=state
        )
        _log.info("gp %s: n=%d -> %.4f kg gain=%.3g state=%s", phase, n, kg, gain, state)
        return Ok(
            LoadSuggestion(
                load_kg=kg,
                text=mass_guidance_text(kg),
                expected_gain=gain,
                expected_half_width=float(after[best]),
                alternatives=alts,
                gp_state=state.value,
            )
        )

    def _noise_var(self, resid: np.ndarray, dof: int) -> float:
        """Noise variance from residuals when there are dof to spare, else the default."""
        if dof >= 1:
            return max(float(resid @ resid) / dof, _NOISE_FLOOR)
        return max(self._noise, _NOISE_FLOOR)

    def _c_optimal(
        self, x: np.ndarray, y: np.ndarray, cand: np.ndarray, span: float
    ) -> tuple[np.ndarray, float, np.ndarray, float]:
        """Score = -posterior slope variance after a rank-one update at each candidate."""
        phi = np.column_stack([np.ones_like(x), x])
        coef, *_ = np.linalg.lstsq(phi, y, rcond=None)
        s2 = self._noise_var(y - phi @ coef, len(x) - 2)
        cov = np.linalg.inv(phi.T @ phi / s2 + PRIOR_PRECISION * np.eye(2))
        pc = np.column_stack([np.ones_like(cand), cand]) @ cov  # rows: (Cov phi_c)^T
        denom = s2 + np.einsum("ij,ij->i", pc, np.column_stack([np.ones_like(cand), cand]))
        var_after = cov[1, 1] - pc[:, 1] ** 2 / denom
        # half-width in response per kg (slope of the normalised load / span)
        hw_now = Z95 * math.sqrt(max(cov[1, 1], 0.0)) / span
        hw_after = Z95 * np.sqrt(np.maximum(var_after, 0.0)) / span
        return -var_after, hw_now, hw_after, s2

    def _gp(
        self, x: np.ndarray, y: np.ndarray, cand: np.ndarray
    ) -> tuple[np.ndarray, float, np.ndarray, float]:
        """Score = predictive variance (info gain 0.5*log(1+var/noise)) under the GP posterior."""
        sf2 = max(float(np.var(y)), _NOISE_FLOOR)
        coef = np.polyfit(x, y, 1)
        s2 = self._noise_var(y - np.polyval(coef, x), len(x) - 2)
        s2 = min(s2, sf2)
        kxx = sf2 * _kernel(x, x, self._kernel, self._length) + s2 * np.eye(len(x))
        kcx = sf2 * _kernel(cand, x, self._kernel, self._length)
        kcc = sf2 * _kernel(cand, cand, self._kernel, self._length)
        sol = np.linalg.solve(kxx, kcx.T)
        post = kcc - kcx @ sol
        var = np.maximum(np.diag(post), 0.0)
        info = 0.5 * np.log1p(var / s2)
        hw_now = Z95 * math.sqrt(float(np.mean(var)))
        after = np.empty(len(cand))
        for i in range(len(cand)):
            red = post[:, i] ** 2 / (var[i] + s2)
            after[i] = Z95 * math.sqrt(
                max(float(np.mean(np.maximum(np.diag(post) - red, 0.0))), 0.0)
            )
        return info, hw_now, after, s2

    @staticmethod
    def _state(n: int, hw_now: float, gain: float, noise: float, y: np.ndarray) -> GpState:
        """Advisory state: unreliable if noise swamps the signal, diminishing if gain is tiny."""
        if n < MIN_JUDGE_POINTS:
            return GpState.COLLECTING
        if noise > max(float(np.var(y)), _NOISE_FLOOR):
            return GpState.UNRELIABLE
        if hw_now > 0 and gain <= DIMINISHING_FRACTION * hw_now:
            return GpState.DIMINISHING
        return GpState.COLLECTING
