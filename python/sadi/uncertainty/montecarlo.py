"""Seeded, resumable, cancellable Monte Carlo propagation plus the three-way cross-check."""

# frob:ticket 01M6W7R2A727G6H66B6FBSDE1R

from __future__ import annotations

import math
from collections.abc import Callable, Mapping, Sequence
from enum import StrEnum

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict
from scipy import stats
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty.covariance import CovarianceRegistry
from sadi.uncertainty.measured import Measured

_log = get_logger(__name__)

DEFAULT_BATCH = 4096
_SQRT6 = math.sqrt(6.0)
_SQRT12 = math.sqrt(12.0)
# Eigenvalues of the correlation matrix below -_PSD_TOL mean it is not positive semi-definite.
_PSD_TOL = 1e-9

CancelCheck = Callable[[], bool]
"""A callable polled between batches; returning True stops the run cooperatively."""


class MonteCarloError(ErrorSet):
    """Failure modes of the Monte Carlo path; the description says what to do next."""

    Cancelled = "Run was cancelled; call run_to again to resume from the kept samples"
    McNotMeasured = "Every argument must be a Measured; wrap raw numbers with Measured.create"
    BadSize = "Sample count must be >= 2 and batch size >= 1; pass larger integers"
    BadCovariance = "Covariance is not positive semi-definite; recheck the declared correlations"
    BadDistribution = "Marginal unsupported for this input (student_t needs dof > 2); use 'normal'"
    McEvalFailed = "Function raised on the sampled inputs; check its domain or the input spreads"
    McNonFinite = "Function produced nan/inf for sampled inputs; narrow the spreads or the domain"


class Marginal(StrEnum):
    """Marginal distribution of one input; correlation enters through a Gaussian copula."""

    NORMAL = "normal"
    UNIFORM = "uniform"
    TRIANGULAR = "triangular"
    STUDENT_T = "student_t"


class McEstimate(BaseModel):
    """Monte Carlo result: mean, sd, 95% percentile interval and their standard errors."""

    model_config = ConfigDict(frozen=True)

    n: int
    seed: int
    mean: float
    std: float
    low: float
    high: float
    se_mean: float
    se_std: float


def _standard_ppf(kind: Marginal, u: NDArray[np.float64], dof: float | None) -> NDArray[np.float64]:
    """Zero-mean unit-variance quantile function of a non-normal marginal at probabilities u."""
    if kind is Marginal.UNIFORM:
        return (u - 0.5) * _SQRT12
    if kind is Marginal.TRIANGULAR:
        return _SQRT6 * np.where(u < 0.5, np.sqrt(2.0 * u) - 1.0, 1.0 - np.sqrt(2.0 * (1.0 - u)))
    assert dof is not None  # validated in McSampler.create
    return np.asarray(stats.t.ppf(u, dof)) / math.sqrt(dof / (dof - 2.0))


class McSampler:
    """Reproducible batch sampler: batch k always uses stream (seed, k), so runs can resume.

    Not thread-safe; use one sampler per job. Recreating it with the same arguments and
    running to the same total reproduces the identical samples.
    """

    def __init__(
        self,
        fn: Callable[..., object],
        means: NDArray[np.float64],
        sds: NDArray[np.float64],
        chol: NDArray[np.float64],
        marginals: Sequence[Marginal],
        dofs: Sequence[float | None],
        seed: int,
        batch_size: int,
    ) -> None:
        """Store the validated model; use `create` or `from_measured` to build one."""
        self._fn = fn
        self._means = means
        self._sds = sds
        self._chol = chol
        self._marginals = tuple(marginals)
        self._dofs = tuple(dofs)
        self._seed = seed
        self._batch = batch_size
        self._outputs: list[NDArray[np.float64]] = []

    @classmethod
    def create(
        cls,
        fn: Callable[..., object],
        means: Sequence[float],
        cov: Sequence[Sequence[float]],
        *,
        seed: int,
        marginals: Sequence[Marginal] | None = None,
        dofs: Sequence[float | None] | None = None,
        batch_size: int = DEFAULT_BATCH,
    ) -> Result[McSampler, MonteCarloError]:
        """Validate the covariance and marginals and build a sampler seeded with `seed`."""
        if batch_size < 1:
            return Err(MonteCarloError.BadSize)
        m = np.asarray(means, dtype=float)
        c = np.asarray(cov, dtype=float)
        d = len(m)
        kinds = tuple(marginals) if marginals is not None else (Marginal.NORMAL,) * d
        dof = tuple(dofs) if dofs is not None else (None,) * d
        if c.shape != (d, d) or len(kinds) != d or len(dof) != d or not np.all(np.isfinite(c)):
            return Err(MonteCarloError.BadCovariance)
        for kind, dd in zip(kinds, dof, strict=True):
            if kind is Marginal.STUDENT_T and (dd is None or not dd > 2.0 or math.isinf(dd)):
                _log.warning("student_t marginal needs finite dof > 2, got %r", dd)
                return Err(MonteCarloError.BadDistribution)
        sds = np.sqrt(np.clip(np.diag(c), 0.0, None))
        safe = np.where(sds > 0, sds, 1.0)
        corr = c / np.outer(safe, safe)
        corr[sds == 0, :] = 0.0
        corr[:, sds == 0] = 0.0
        np.fill_diagonal(corr, 1.0)
        w, v = np.linalg.eigh((corr + corr.T) / 2.0)
        if w.min(initial=0.0) < -_PSD_TOL:
            _log.warning("covariance not PSD: min eigenvalue %g", w.min())
            return Err(MonteCarloError.BadCovariance)
        chol = v * np.sqrt(np.clip(w, 0.0, None))
        _log.info("mc sampler: d=%d seed=%d marginals=%s", d, seed, [k.value for k in kinds])
        return Ok(cls(fn, m, sds, chol, kinds, dof, seed, batch_size))

    @classmethod
    def from_measured(
        cls,
        fn: Callable[..., object],
        args: Sequence[Measured],
        registry: CovarianceRegistry,
        *,
        seed: int,
        marginals: Sequence[Marginal] | None = None,
        batch_size: int = DEFAULT_BATCH,
    ) -> Result[McSampler, MonteCarloError]:
        """Build a sampler from Measured inputs using the registry's full covariance."""
        if not all(isinstance(a, Measured) for a in args):
            return Err(MonteCarloError.McNotMeasured)
        cov = [[registry.covariance(a.id, b.id) for b in args] for a in args]
        return cls.create(
            fn,
            [a.value for a in args],
            cov,
            seed=seed,
            marginals=marginals,
            dofs=[a.dof for a in args],
            batch_size=batch_size,
        )

    @property
    def n(self) -> int:
        """Number of samples drawn so far."""
        return len(self._outputs) * self._batch

    def _draw_inputs(self, k: int) -> NDArray[np.float64]:
        """Draw input batch k from its own stream (seed, k)."""
        rng = np.random.default_rng(np.random.SeedSequence(self._seed, spawn_key=(k,)))
        z = rng.standard_normal((self._batch, len(self._means))) @ self._chol.T
        x = z
        if any(m is not Marginal.NORMAL for m in self._marginals):
            u = np.clip(stats.norm.cdf(z), 1e-12, 1.0 - 1e-12)
            x = np.column_stack(
                [
                    z[:, j]
                    if kind is Marginal.NORMAL
                    else _standard_ppf(kind, u[:, j], self._dofs[j])
                    for j, kind in enumerate(self._marginals)
                ]
            )
        return self._means + self._sds * x

    def _evaluate(self, x: NDArray[np.float64]) -> Result[NDArray[np.float64], MonteCarloError]:
        """Run `fn` vectorised over the batch, falling back to a row loop for branchy code."""

        def vectorised() -> NDArray[np.float64]:
            with np.errstate(all="ignore"):
                y = np.asarray(self._fn(*x.T), dtype=float)
            return np.broadcast_to(y, (len(x),)).copy()

        def rowwise() -> NDArray[np.float64]:
            with np.errstate(all="ignore"):
                return np.array([float(np.asarray(self._fn(*row))) for row in x])

        out = Result.catch(vectorised, Exception, on_error=lambda exc: MonteCarloError.McEvalFailed)
        if isinstance(out, Err):
            _log.debug("vectorised evaluation failed; using row loop")
            out = Result.catch(
                rowwise, Exception, on_error=lambda exc: MonteCarloError.McEvalFailed
            )
        if isinstance(out, Err):
            return out
        if not np.all(np.isfinite(out.danger_ok)):
            _log.warning("non-finite function output in sampled batch")
            return Err(MonteCarloError.McNonFinite)
        return out

    def run_to(
        self, total: int, cancel: CancelCheck | None = None
    ) -> Result[McEstimate, MonteCarloError]:
        """Draw batches until at least `total` samples exist and return the estimate.

        `cancel` is polled before every batch; if it returns True the run stops with
        `Cancelled` and all completed batches are kept, so a later call resumes.
        """
        if total < 2:
            return Err(MonteCarloError.BadSize)
        while self.n < total:
            if cancel is not None and cancel():
                _log.info("mc cancelled at n=%d", self.n)
                return Err(MonteCarloError.Cancelled)
            y = self._evaluate(self._draw_inputs(len(self._outputs)))
            if isinstance(y, Err):
                return Err(y.danger_err)
            self._outputs.append(y.danger_ok)
            _log.debug("mc batch %d done, n=%d", len(self._outputs), self.n)
        return Ok(self.estimate())

    def estimate(self) -> McEstimate:
        """Summarise all samples drawn so far (requires at least two)."""
        y = np.concatenate(self._outputs)
        n = len(y)
        sd = float(np.std(y, ddof=1))
        low, high = (float(q) for q in np.percentile(y, [2.5, 97.5]))
        return McEstimate(
            n=n,
            seed=self._seed,
            mean=float(np.mean(y)),
            std=sd,
            low=low,
            high=high,
            se_mean=sd / math.sqrt(n),
            se_std=sd / math.sqrt(2.0 * (n - 1)),
        )


class MethodEstimate(BaseModel):
    """One method's value and standard uncertainty with their sampling errors (0 if exact)."""

    model_config = ConfigDict(frozen=True)

    method: str
    value: float
    std_unc: float
    se_value: float = 0.0
    se_std: float = 0.0


def from_mc(est: McEstimate) -> MethodEstimate:
    """Convert a Monte Carlo estimate to a cross-check entry."""
    return MethodEstimate(
        method="mc", value=est.mean, std_unc=est.std, se_value=est.se_mean, se_std=est.se_std
    )


class Disagreement(BaseModel):
    """Two methods differing on `quantity` by more than the tolerance."""

    model_config = ConfigDict(frozen=True)

    a: str
    b: str
    quantity: str
    difference: float
    tolerance: float


class CrossCheck(BaseModel):
    """Outcome of comparing methods: `agree` is True when no pair exceeds its tolerance."""

    model_config = ConfigDict(frozen=True)

    agree: bool
    findings: tuple[Disagreement, ...]


def cross_check(
    estimates: Mapping[str, MethodEstimate] | Sequence[MethodEstimate],
    *,
    rel_tol: float = 0.05,
    k_sigma: float = 4.0,
) -> CrossCheck:
    """Flag pairs of methods whose value or std_unc differ beyond rel_tol plus k_sigma*SE.

    The tolerance for a pair is `rel_tol * max(|x|, |y|) + k_sigma * hypot(se_x, se_y)`, so a
    sampled method is only flagged when the gap exceeds both model error and sampling noise.
    """
    items = list(estimates.values()) if isinstance(estimates, Mapping) else list(estimates)
    findings: list[Disagreement] = []
    for i, p in enumerate(items):
        for q in items[i + 1 :]:
            for name, x, y, sx, sy in (
                ("value", p.value, q.value, p.se_value, q.se_value),
                ("std_unc", p.std_unc, q.std_unc, p.se_std, q.se_std),
            ):
                tol = rel_tol * max(abs(x), abs(y)) + k_sigma * math.hypot(sx, sy)
                if abs(x - y) > tol:
                    _log.warning("cross-check: %s vs %s differ on %s", p.method, q.method, name)
                    findings.append(
                        Disagreement(
                            a=p.method, b=q.method, quantity=name, difference=x - y, tolerance=tol
                        )
                    )
    return CrossCheck(agree=not findings, findings=tuple(findings))
