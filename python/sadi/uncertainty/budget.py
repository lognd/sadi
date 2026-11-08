"""Uncertainty budget: per-input sensitivity, variance contribution (with covariance), ranking."""

# frob:ticket 01M6W7R2BS0R89GW39HM0XPX0J

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from sadi.logging_setup import get_logger
from sadi.uncertainty.covariance import CovarianceRegistry
from sadi.uncertainty.measured import Measured

_log = get_logger(__name__)


class BudgetRow(BaseModel):
    """One input's line in the budget: value, u, sensitivity and variance share."""

    model_config = ConfigDict(frozen=True)

    name: str
    id: str
    value: float
    unit: str
    std_unc: float
    sensitivity: float
    direct: float
    cross: float
    contribution: float
    percent: float
    rank: int


class Budget(BaseModel):
    """Ranked per-input budget whose contributions sum to the total variance."""

    model_config = ConfigDict(frozen=True)

    rows: tuple[BudgetRow, ...]
    total_variance: float
    total_std_unc: float

    @property
    def dominant(self) -> BudgetRow | None:
        """The rank-1 row (largest absolute contribution), or None for an empty budget."""
        return self.rows[0] if self.rows else None

    def payload(self) -> dict[str, Any]:
        """Return a JSON-safe dict for the UI dominant-input panel."""
        dom = self.dominant
        return {
            "total_variance": self.total_variance,
            "total_std_unc": self.total_std_unc,
            "dominant": dom.name if dom else None,
            "rows": [r.model_dump(mode="json") for r in self.rows],
        }


def build_budget(
    names: Sequence[str],
    args: Sequence[Measured],
    sensitivities: Sequence[float],
    registry: CovarianceRegistry,
) -> Budget:
    """Build the budget for inputs `args` with partials `sensitivities`.

    Row i contributes c_i * sum_j c_j cov(x_i, x_j): its own c_i^2 u_i^2 (`direct`) plus
    the covariance cross terms with every other input (`cross`), so rows sum to J C J^T.
    """
    c = list(sensitivities)
    raw: list[tuple[float, float]] = []
    for i, a in enumerate(args):
        direct = c[i] * c[i] * registry.covariance(a.id, a.id)
        cross = math.fsum(
            c[i] * c[j] * registry.covariance(a.id, b.id) for j, b in enumerate(args) if j != i
        )
        raw.append((direct, cross))
    total = math.fsum(d + x for d, x in raw)
    order = sorted(range(len(args)), key=lambda i: -abs(raw[i][0] + raw[i][1]))
    rows = []
    for rank, i in enumerate(order, start=1):
        direct, cross = raw[i]
        contrib = direct + cross
        rows.append(
            BudgetRow(
                name=names[i],
                id=args[i].id,
                value=args[i].value,
                unit=args[i].unit,
                std_unc=args[i].std_unc,
                sensitivity=c[i],
                direct=direct,
                cross=cross,
                contribution=contrib,
                percent=100.0 * contrib / total if total > 0 else 0.0,
                rank=rank,
            )
        )
    total = max(0.0, total)
    _log.info("budget: %d inputs, u^2=%g", len(rows), total)
    return Budget(rows=tuple(rows), total_variance=total, total_std_unc=math.sqrt(total))
