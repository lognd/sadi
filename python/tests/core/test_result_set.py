"""ResultSet lookup: named values are found, uncomputed names are None."""

# frob:ticket 01M6XAY79MWPV07858YAKSBJQ6
from __future__ import annotations

from sadi.core.results import ResultSet, make_result


# frob:tests python/sadi/core/results.py::ResultSet.get
def test_get_returns_named_value_or_none() -> None:
    """get() finds a value by name and returns None for names not computed yet."""
    e = make_result("E", 70.0e9, 1.0e9, "Pa", dof=10.0).danger_ok
    nu = make_result("nu", 0.33, 0.01, "dimensionless", dof=10.0).danger_ok
    rs = ResultSet(n_points=3, values=(e, nu), pending=("G",))
    assert rs.get("E") is e and rs.get("nu") is nu
    assert rs.get("G") is None
    assert ResultSet().get("E") is None
