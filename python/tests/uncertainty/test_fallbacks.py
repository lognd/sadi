"""Tests for the numeric-derivative and Monte Carlo fallbacks and the cross-check helper."""

# frob:ticket 01M6W7R2A727G6H66B6FBSDE1R

from __future__ import annotations

import ast
import math
from pathlib import Path

import numpy as np
from hypothesis import given, settings
from hypothesis import strategies as st
from typani import Err, Ok

from sadi.uncertainty import (
    CovarianceRegistry,
    Marginal,
    McConfig,
    McSampler,
    Measured,
    MethodEstimate,
    MonteCarloError,
    NumericError,
    UncertainError,
    cross_check,
    uncertain,
)
from sadi.uncertainty.montecarlo import from_mc
from sadi.uncertainty.numeric import central_difference, complex_step, gradient

MC_DIR = Path(__file__).resolve().parents[2] / "sadi" / "uncertainty"
K = 6.0  # deterministic seeds, so a 6-sigma CI-aware band is generous but still meaningful


def _mk(reg: CovarianceRegistry, v: float, u: float, unit: str = "m") -> Measured:
    """Create a Measured in registry `reg`."""
    return Measured.create(v, u, unit, registry=reg).unwrap()


def _sampler(fn, means, cov, seed=7, **kw) -> McSampler:
    """Build a sampler or fail the test."""
    return McSampler.create(fn, means, cov, seed=seed, **kw).unwrap()


# ---- numeric derivatives (criterion 1) ---------------------------------------


# frob:tests python/sadi/uncertainty/numeric.py::gradient
def test_complex_step_used_for_smooth_numpy_function() -> None:
    """Analytic numpy functions take the complex-step path and match exact partials."""
    g = gradient(lambda x, y: np.sin(x) * np.exp(y), [0.7, -0.3]).unwrap()
    assert g.methods == ("complex", "complex")
    assert math.isclose(g.gradient[0], math.cos(0.7) * math.exp(-0.3), rel_tol=1e-12)
    assert math.isclose(g.gradient[1], math.sin(0.7) * math.exp(-0.3), rel_tol=1e-12)


# frob:tests python/sadi/uncertainty/numeric.py::central_difference
def test_branching_function_falls_back_to_central_differences() -> None:
    """A Python branch breaks complex input; adaptive central differences recover the slope."""

    def f(x: float, y: float) -> float:
        return x**2 * y if x > 0 else -x

    g = gradient(f, [3.0, 2.0]).unwrap()
    assert g.methods == ("central", "central")
    assert math.isclose(g.gradient[0], 12.0, rel_tol=1e-8)
    assert math.isclose(g.gradient[1], 9.0, rel_tol=1e-8)
    assert all(e >= 0.0 for e in g.errors)


# frob:tests python/sadi/uncertainty/numeric.py::_derivative
def test_abs_rejects_complex_step_that_returns_zero() -> None:
    """np.abs returns a real modulus under complex-step (a wrong 0); the cross-check catches it."""
    g = gradient(lambda x: np.abs(x), [2.0]).unwrap()
    assert g.methods == ("central",)
    assert math.isclose(g.gradient[0], 1.0, rel_tol=1e-8)


# frob:tests python/sadi/uncertainty/numeric.py::complex_step
def test_complex_step_error_on_unsupported_function() -> None:
    """Comparisons on complex input raise; complex_step returns a typed error."""
    r = complex_step(lambda x: x if x > 0 else 0.0, [1.0], 0)
    assert isinstance(r, Err) and r.danger_err is NumericError.NumEvalFailed


# frob:tests python/sadi/uncertainty/numeric.py::gradient
def test_numeric_errors_are_typed() -> None:
    """Singular and raising functions give Err values, never exceptions."""
    r = gradient(lambda x: np.log(x), [0.0])
    assert isinstance(r, Err) and r.danger_err is NumericError.NumNonFinite
    r2 = gradient(lambda x: 1 / 0, [1.0])
    assert isinstance(r2, Err) and r2.danger_err is NumericError.NumEvalFailed


# frob:tests python/sadi/uncertainty/numeric.py::central_difference
@settings(max_examples=40, deadline=None)
@given(
    a=st.floats(-5, 5),
    b=st.floats(-5, 5),
    x=st.floats(-10, 10),
)
def test_central_difference_matches_cubic_derivative(a: float, b: float, x: float) -> None:
    """Ridders differences recover d/dx (a x^3 + b x) = 3 a x^2 + b to high accuracy."""
    r = central_difference(lambda t: a * t**3 + b * t, [x], 0)
    assert isinstance(r, Ok)
    d, err = r.danger_ok
    exact = 3 * a * x**2 + b
    assert abs(d - exact) <= 1e-7 * max(1.0, abs(exact)) + 10 * err


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
def test_decorator_numeric_matches_analytic_and_auto_falls_back() -> None:
    """method="numeric" agrees with the sympy path; "auto" falls back for math.* functions."""
    reg = CovarianceRegistry()
    x, y = _mk(reg, 1.3, 0.05), _mk(reg, 0.8, 0.02)
    sym = uncertain(lambda a, b: a * b**2, unit="m**3", registry=reg)(x, y).unwrap()
    num = uncertain(lambda a, b: a * b**2, unit="m**3", registry=reg, method="numeric")(
        x, y
    ).unwrap()
    assert math.isclose(sym.std_unc, num.std_unc, rel_tol=1e-8)
    assert num.provenance.derivation == "uncertain-numeric(<lambda>)"

    traced = uncertain(lambda a: math.sin(a), unit="m", registry=reg)
    auto = traced(x).unwrap()
    assert math.isclose(auto.value, math.sin(1.3), rel_tol=1e-12)
    assert math.isclose(auto.std_unc, abs(math.cos(1.3)) * 0.05, rel_tol=1e-8)
    strict = uncertain(lambda a: math.sin(a), unit="m", registry=reg, method="analytic")(x)
    assert isinstance(strict, Err) and strict.danger_err is UncertainError.Untraceable


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
def test_numeric_path_honours_correlation_and_arity() -> None:
    """Numeric partials go through the same full-covariance RSS; bad arguments are typed."""
    reg = CovarianceRegistry()
    x, y = _mk(reg, 2.0, 0.1), _mk(reg, 3.0, 0.2)
    x.correlate(y, 0.6, registry=reg).unwrap()
    f = uncertain(lambda a, b: a - b if a > 0 else b, unit="m", registry=reg, method="numeric")
    out = f(x, y).unwrap()
    expect = math.sqrt(0.1**2 + 0.2**2 - 2 * 0.6 * 0.1 * 0.2)
    assert math.isclose(out.std_unc, expect, rel_tol=1e-8)
    assert isinstance(f(x), Err)
    assert isinstance(f(x, 3.0), Err)  # type: ignore[arg-type]


# ---- Monte Carlo (criterion 2) ----------------------------------------------


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.run_to
def test_seeded_and_reproducible() -> None:
    """Same seed gives bit-identical estimates; a different seed does not."""
    cov = [[0.04, 0.01], [0.01, 0.09]]

    def run(seed: int):
        return _sampler(lambda a, b: a * b, [2.0, 3.0], cov, seed=seed).run_to(20000).unwrap()

    assert run(11) == run(11)
    assert run(11).mean != run(12).mean


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.run_to
def test_resumable_equals_single_run() -> None:
    """Refining 4096 -> 16384 -> 40000 matches a fresh run to the same total, bit for bit."""
    cov = [[0.04, 0.0], [0.0, 0.09]]
    s = _sampler(lambda a, b: a + b**2, [1.0, 2.0], cov)
    first = s.run_to(4096).unwrap()
    assert first.n == 4096
    s.run_to(16384).unwrap()
    refined = s.run_to(40000).unwrap()
    fresh = _sampler(lambda a, b: a + b**2, [1.0, 2.0], cov).run_to(40000).unwrap()
    assert refined == fresh
    assert refined.n == s.n == 40960
    assert refined.se_mean < first.se_mean


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.run_to
def test_cancel_is_cooperative_and_resumable() -> None:
    """A cancel check stops between batches, keeps finished batches and lets a rerun resume."""
    cov = [[1.0]]
    polls = {"n": 0}

    def cancel() -> bool:
        polls["n"] += 1
        return polls["n"] > 3

    s = _sampler(lambda a: a, [0.0], cov, batch_size=1000)
    r = s.run_to(100_000, cancel)
    assert isinstance(r, Err) and r.danger_err is MonteCarloError.Cancelled
    assert s.n == 3000
    done = s.run_to(10_000).unwrap()
    assert done == _sampler(lambda a: a, [0.0], cov, batch_size=1000).run_to(10_000).unwrap()


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.create
@settings(max_examples=25, deadline=None)
@given(
    m1=st.floats(-5, 5),
    m2=st.floats(-5, 5),
    s1=st.floats(0.1, 2.0),
    s2=st.floats(0.1, 2.0),
    rho=st.floats(-0.95, 0.95),
    c1=st.floats(-3, 3),
    c2=st.floats(-3, 3),
)
def test_gaussian_linear_matches_analytic_within_ci(
    m1: float, m2: float, s1: float, s2: float, rho: float, c1: float, c2: float
) -> None:
    """For f = c1 x + c2 y the MC mean, sd and 95% interval match the exact Gaussian result."""
    cov = [[s1**2, rho * s1 * s2], [rho * s1 * s2, s2**2]]
    est = _sampler(lambda x, y: c1 * x + c2 * y, [m1, m2], cov).run_to(30000).unwrap()
    mean = c1 * m1 + c2 * m2
    sd = math.sqrt(c1**2 * s1**2 + c2**2 * s2**2 + 2 * c1 * c2 * rho * s1 * s2)
    assert abs(est.mean - mean) <= K * est.se_mean + 1e-12
    assert abs(est.std - sd) <= K * est.se_std + 1e-12
    # percentile endpoints have SE ~ sd * 0.0114 * sqrt(1/n)*~2.1; allow 5% of sd
    assert abs(est.low - (mean - 1.959964 * sd)) <= 0.06 * sd + 1e-12
    assert abs(est.high - (mean + 1.959964 * sd)) <= 0.06 * sd + 1e-12


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.create
def test_non_gaussian_marginals_match_moments() -> None:
    """Uniform, triangular and Student-t marginals keep the stated mean and sd."""
    for kind, dof in (
        (Marginal.UNIFORM, None),
        (Marginal.TRIANGULAR, None),
        (Marginal.STUDENT_T, 12.0),
    ):
        est = _sampler(lambda a: a, [5.0], [[0.25]], marginals=[kind], dofs=[dof]).run_to(80000)
        e = est.unwrap()
        assert abs(e.mean - 5.0) <= K * e.se_mean, kind
        assert abs(e.std - 0.5) <= 0.02, kind  # t has a heavier tail, so a looser sd band


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.create
def test_non_gaussian_marginals_preserve_correlation() -> None:
    """The Gaussian copula keeps the requested correlation for non-normal marginals."""
    cov = [[1.0, 0.8], [0.8, 1.0]]
    s = _sampler(lambda a, b: a * b, [0.0, 0.0], cov, marginals=[Marginal.UNIFORM] * 2)
    est = s.run_to(60000).unwrap()
    # E[ab] = cov for zero means (approximately; copula correlation is slightly attenuated)
    assert 0.7 < est.mean < 0.85


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.create
def test_invalid_models_are_typed_errors() -> None:
    """Non-PSD covariance, bad dof and bad sizes return Err, not exceptions."""
    bad = McSampler.create(lambda a, b: a, [0.0, 0.0], [[1.0, 2.0], [2.0, 1.0]], seed=1)
    assert isinstance(bad, Err) and bad.danger_err is MonteCarloError.BadCovariance
    t = McSampler.create(lambda a: a, [0.0], [[1.0]], seed=1, marginals=[Marginal.STUDENT_T])
    assert isinstance(t, Err) and t.danger_err is MonteCarloError.BadDistribution
    size = McSampler.create(lambda a: a, [0.0], [[1.0]], seed=1, batch_size=0)
    assert isinstance(size, Err) and size.danger_err is MonteCarloError.BadSize
    ok = _sampler(lambda a: a, [0.0], [[1.0]])
    few = ok.run_to(1)
    assert isinstance(few, Err) and few.danger_err is MonteCarloError.BadSize


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.run_to
def test_branchy_function_and_failures() -> None:
    """Branching code falls back to a row loop; exceptions and nan are typed errors."""
    branchy = _sampler(lambda a: a if a > 0 else 0.0, [10.0], [[1.0]]).run_to(8000).unwrap()
    assert abs(branchy.mean - 10.0) <= K * branchy.se_mean
    raising = _sampler(lambda a: 1 / 0, [1.0], [[1.0]]).run_to(100)
    assert isinstance(raising, Err) and raising.danger_err is MonteCarloError.McEvalFailed
    nan = _sampler(lambda a: np.log(a), [0.0], [[1.0]]).run_to(100)
    assert isinstance(nan, Err) and nan.danger_err is MonteCarloError.McNonFinite


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.__call__
def test_decorator_mc_uses_registry_covariance() -> None:
    """method="mc" returns a Measured with mean and sd from the correlated sampling."""
    reg = CovarianceRegistry()
    x, y = _mk(reg, 10.0, 0.5), _mk(reg, 4.0, 0.4)
    x.correlate(y, -0.5, registry=reg).unwrap()
    f = uncertain(
        lambda a, b: 2 * a + 3 * b,
        unit="m",
        registry=reg,
        method="mc",
        mc=McConfig(n=60000, seed=5),
    )
    out = f(x, y).unwrap()
    sd = math.sqrt(4 * 0.25 + 9 * 0.16 + 2 * 6 * -0.5 * 0.5 * 0.4)
    assert abs(out.value - 32.0) <= 0.02
    assert abs(out.std_unc - sd) <= 0.02
    assert "seed=5" in (out.provenance.derivation or "")
    assert isinstance(f(x), Err)
    est = f.monte_carlo(x, y, n=5000, seed=1, cancel=lambda: True)
    assert isinstance(est, Err) and est.danger_err is MonteCarloError.Cancelled


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler
def test_montecarlo_module_is_web_and_store_free() -> None:
    """The MC and numeric modules import neither sadi.store nor any web framework."""
    banned = ("sadi.store", "sadi.web", "fastapi", "starlette", "flask")
    for name in ("montecarlo.py", "numeric.py"):
        tree = ast.parse((MC_DIR / name).read_text())
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            assert not [m for m in mods if m.startswith(banned)], (name, mods)


# ---- cross-check (criterion 3) -----------------------------------------------


# frob:tests python/sadi/uncertainty/montecarlo.py::cross_check
def test_cross_check_flags_only_real_disagreement() -> None:
    """Agreement within rel_tol plus k*SE passes; a gap beyond it is reported per quantity."""
    a = MethodEstimate(method="analytic", value=10.0, std_unc=1.0)
    b = MethodEstimate(method="numeric", value=10.0 + 1e-9, std_unc=1.0)
    m = MethodEstimate(method="mc", value=10.2, std_unc=1.03, se_value=0.1, se_std=0.01)
    assert cross_check([a, b, m]).agree
    far = MethodEstimate(method="mc", value=10.0, std_unc=1.5, se_std=0.01)
    report = cross_check({"a": a, "mc": far})
    assert not report.agree
    assert [(f.a, f.b, f.quantity) for f in report.findings] == [("analytic", "mc", "std_unc")]
    assert report.findings[0].difference == -0.5


# frob:tests python/sadi/uncertainty/uncertain.py::Uncertain.cross_check
def test_decorator_cross_check_linear_agrees_nonlinear_flags() -> None:
    """Linear functions agree across all three methods; a strongly nonlinear one is flagged."""
    reg = CovarianceRegistry()
    x, y = _mk(reg, 5.0, 0.2), _mk(reg, 2.0, 0.1)
    cfg = McConfig(n=60000, seed=3)
    lin = uncertain(lambda a, b: 3 * a - b, unit="m", registry=reg, mc=cfg)
    report = lin.cross_check(x, y).unwrap()
    assert report.agree
    wide = _mk(reg, 1.0, 1.0)
    sq = uncertain(lambda a: a**2, unit="m**2", registry=reg, mc=cfg)
    flagged = sq.cross_check(wide).unwrap()
    assert not flagged.agree
    assert {f.quantity for f in flagged.findings} == {"std_unc"} | {
        f.quantity for f in flagged.findings
    }
    assert any(
        f.a == "analytic" and f.b == "mc" and f.quantity == "std_unc" for f in flagged.findings
    )


# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.n
# frob:tests python/sadi/uncertainty/montecarlo.py::McSampler.__init__
# frob:tests python/sadi/uncertainty/montecarlo.py::from_mc
def test_sample_count_and_from_mc_adapter() -> None:
    """`n` tracks drawn samples and from_mc turns an McEstimate into a MethodEstimate."""
    s = _sampler(lambda a: a, [1.0], [[0.25]], batch_size=500)
    assert s.n == 0
    est = s.run_to(1000).unwrap()
    assert s.n == 1000
    me = from_mc(est)
    assert me.method == "mc" and me.value == est.mean and me.std_unc == est.std


# frob:ticket 01M6WJQ4A9Q9MTK0XQQSJ9VQC9
# frob:tests python/sadi/uncertainty/numeric.py::gradient
def test_gradient_small_divisor_does_not_cross_pole() -> None:
    """Steps scale with |x|, so a/b at b=1e-3 converges to (1/b, -a/b^2)."""
    result = gradient(lambda a, b: a / b, [1.0, 1e-3])
    assert isinstance(result, Ok)
    da, db = result.danger_ok.gradient
    assert math.isclose(da, 1e3, rel_tol=1e-4)
    assert math.isclose(db, -1e6, rel_tol=1e-4)
