"""Registry lifetime and register_derived scaling tests."""

# frob:ticket 7VE6XWX

from __future__ import annotations

import gc

from typani import Ok

from sadi.uncertainty import CovarianceRegistry, Measured


def _mk(reg: CovarianceRegistry, v: float = 1.0, u: float = 0.1) -> Measured:
    return Measured.create(v, u, "m", registry=reg).danger_ok


# frob:tests python/sadi/uncertainty/covariance.py::CovarianceRegistry.release
# frob:tests python/sadi/uncertainty/covariance.py::CovarianceRegistry.forget
def test_registry_bounded_after_dropping_measured() -> None:
    reg = CovarianceRegistry()
    keep = _mk(reg)
    for _ in range(500):
        t = _mk(reg)
        assert isinstance(keep.correlate(t, 0.5, registry=reg), Ok)
        del t
    gc.collect()
    assert reg.ids() == [keep.id]
    assert not reg._cov and not reg._nbrs  # noqa: SLF001


# frob:tests python/sadi/uncertainty/covariance.py::CovarianceRegistry.register_derived
def test_register_derived_cost_independent_of_unrelated_entries() -> None:
    def count_ops(n_unrelated: int) -> int:
        reg = CovarianceRegistry()
        noise = [_mk(reg) for _ in range(n_unrelated)]
        a, b = _mk(reg), _mk(reg)
        calls = 0
        orig = reg.covariance

        def spy(x: str, y: str) -> float:
            nonlocal calls
            calls += 1
            return orig(x, y)

        reg.covariance = spy  # type: ignore[method-assign]
        reg.register_derived("d", [(a.id, 1.0), (b.id, 2.0)])
        assert noise
        return calls

    assert count_ops(5) == count_ops(500)
