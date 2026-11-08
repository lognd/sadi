"""Shared covariance registry keyed by Measured id, plus first-order variance combination."""

# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H

from __future__ import annotations

import math
import threading
from collections.abc import Sequence

from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.uncertainty.errors import UncertaintyError

_log = get_logger(__name__)


class CovarianceRegistry:
    """Thread-safe store of variances and pairwise covariances keyed by quantity id."""

    def __init__(self) -> None:
        """Create an empty registry."""
        self._lock = threading.RLock()
        self._var: dict[str, float] = {}
        self._cov: dict[frozenset[str], float] = {}
        self._nbrs: dict[str, set[str]] = {}  # ids with a stored nonzero covariance
        self._refs: dict[str, int] = {}

    def register(self, ident: str, variance: float) -> None:
        """Record (or replace) the variance of `ident`."""
        with self._lock:
            self._var[ident] = variance
            _log.debug("registered %s var=%g", ident, variance)

    def retain(self, ident: str) -> None:
        """Add one owner of `ident`; pair each call with `release` (e.g. via weakref.finalize)."""
        with self._lock:
            self._refs[ident] = self._refs.get(ident, 0) + 1

    def release(self, ident: str) -> None:
        """Drop one owner of `ident`; forget it once no owners remain."""
        with self._lock:
            n = self._refs.get(ident, 0) - 1
            if n > 0:
                self._refs[ident] = n
                return
            self._refs.pop(ident, None)
            self.forget(ident)

    def forget(self, ident: str) -> None:
        """Remove `ident` and every covariance involving it (cost ~ its neighbour count)."""
        with self._lock:
            self._var.pop(ident, None)
            for w in self._nbrs.pop(ident, ()):
                self._cov.pop(frozenset((ident, w)), None)
                peers = self._nbrs.get(w)
                if peers is not None:
                    peers.discard(ident)
                    if not peers:
                        del self._nbrs[w]
            _log.debug("forgot %s", ident)

    def _store_cov(self, a: str, b: str, cov: float) -> None:
        """Store cov(a, b) and index the pair for neighbour lookup (lock held)."""
        self._cov[frozenset((a, b))] = cov
        self._nbrs.setdefault(a, set()).add(b)
        self._nbrs.setdefault(b, set()).add(a)

    def known(self, ident: str) -> bool:
        """Return True if `ident` has a registered variance."""
        with self._lock:
            return ident in self._var

    def ids(self) -> list[str]:
        """Return all registered ids."""
        with self._lock:
            return list(self._var)

    def set_covariance(self, a: str, b: str, cov: float) -> Result[None, UncertaintyError]:
        """Set cov(a, b); rejects non-finite values and |cov| > sqrt(var_a var_b)."""
        with self._lock:
            if a == b or a not in self._var or b not in self._var or not math.isfinite(cov):
                _log.warning("set_covariance rejected for %s,%s", a, b)
                return Err(UncertaintyError.InvalidCorrelation)
            bound = math.sqrt(self._var[a] * self._var[b])
            if abs(cov) > bound * (1 + 1e-12):
                _log.warning("covariance %g exceeds bound %g for %s,%s", cov, bound, a, b)
                return Err(UncertaintyError.InvalidCorrelation)
            self._store_cov(a, b, cov)
            _log.debug("cov(%s,%s)=%g", a, b, cov)
            return Ok(None)

    def set_correlation(self, a: str, b: str, rho: float) -> Result[None, UncertaintyError]:
        """Set the correlation coefficient of a and b, rho in [-1, 1]."""
        with self._lock:
            if not (math.isfinite(rho) and -1.0 <= rho <= 1.0):
                return Err(UncertaintyError.InvalidCorrelation)
            if a not in self._var or b not in self._var:
                return Err(UncertaintyError.InvalidCorrelation)
            return self.set_covariance(a, b, rho * math.sqrt(self._var[a] * self._var[b]))

    def covariance(self, a: str, b: str) -> float:
        """Return cov(a, b); the variance when a == b, 0.0 when unrelated or unknown."""
        with self._lock:
            if a == b:
                return self._var.get(a, 0.0)
            return self._cov.get(frozenset((a, b)), 0.0)

    def correlation(self, a: str, b: str) -> float:
        """Return the correlation of a and b, 0.0 if either has zero variance."""
        with self._lock:
            denom = math.sqrt(self.covariance(a, a) * self.covariance(b, b))
            return self.covariance(a, b) / denom if denom > 0 else 0.0

    def register_derived(self, ident: str, terms: Sequence[tuple[str, float]]) -> float:
        """Register `ident` = f(x_i) with partials c_i and return its variance.

        Stores cov(ident, w) = sum_i c_i cov(x_i, w) for every known w, so later
        combinations of derived and source quantities keep their correlation.
        Only ids with a stored covariance to some source can be nonzero, so the cost
        follows the sources' neighbourhood, not the registry size.
        """
        with self._lock:
            var = max(0.0, first_order_variance(self, terms))
            cands: set[str] = set()
            for x, _ in terms:
                cands.add(x)
                cands.update(self._nbrs.get(x, ()))
            others = [w for w in cands if w != ident and w in self._var]
            covs = {w: sum(c * self.covariance(x, w) for x, c in terms) for w in others}
            self.register(ident, var)
            for w, cov in covs.items():
                if cov != 0.0:
                    self._store_cov(ident, w, cov)
            return var


def first_order_variance(registry: CovarianceRegistry, terms: Sequence[tuple[str, float]]) -> float:
    """Return sum_ij c_i c_j cov(x_i, x_j) for (id, partial) terms (full-covariance RSS)."""
    total = 0.0
    for i, (xi, ci) in enumerate(terms):
        total += ci * ci * registry.covariance(xi, xi)
        for xj, cj in terms[i + 1 :]:
            total += 2.0 * ci * cj * registry.covariance(xi, xj)
    return total


DEFAULT_REGISTRY = CovarianceRegistry()
