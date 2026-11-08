"""LCTT nominal budgets come from the public uncertainty engine and are well formed."""

# frob:ticket 01M6WV1BBQYWGMK7W6KDD8P2N2

from __future__ import annotations

from sadi.core.lab import BudgetedLab
from sadi.labs.lctt.budgets import nominal_budgets
from sadi.labs.lctt.lab import LcttLab


# frob:tests python/sadi/labs/lctt/budgets.py::nominal_budgets
def test_nominal_budgets_ranked_and_consistent() -> None:
    """Stress and E budgets have ranked rows summing to the total variance."""
    got = nominal_budgets()
    assert [b.result for b in got] == ["stress", "E"]
    for b in got:
        assert b.budget.dominant is not None and b.budget.dominant.rank == 1
        total = sum(r.contribution for r in b.budget.rows)
        assert abs(total - b.budget.total_variance) <= 1e-9 * b.budget.total_variance
        assert b.latex


# frob:tests python/sadi/labs/lctt/lab.py::LcttLab.budgets
# frob:tests python/sadi/core/lab.py::BudgetedLab.budgets
def test_lctt_lab_is_budgeted() -> None:
    """The lctt lab satisfies BudgetedLab and returns the nominal budgets."""
    lab = LcttLab()
    assert isinstance(lab, BudgetedLab)
    assert len(lab.budgets()) == 2
