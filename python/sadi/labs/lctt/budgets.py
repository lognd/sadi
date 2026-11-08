"""LCTT nominal uncertainty budgets: stress and chord modulus at representative inputs."""

# frob:ticket 01M6WV1BBQYWGMK7W6KDD8P2N2

from __future__ import annotations

from typani import Err

from sadi.core.lab import LabBudget
from sadi.labs.lctt.loading import cross_area, load_force, stress
from sadi.labs.lctt.modulus import chord_modulus
from sadi.logging_setup import get_logger
from sadi.uncertainty import Measured

_log = get_logger(__name__)


def _m(value: float, unc: float, unit: str) -> Measured:
    """Build a Measured from literals known to be valid (a failure is a programmer bug)."""
    made = Measured.create(value, unc, unit)
    assert not isinstance(made, Err), made
    return made.danger_ok


def nominal_budgets() -> list[LabBudget]:
    """Budgets for stress (F/A) and chord modulus at nominal inputs; skips any that fail."""
    force = load_force(_m(2.0, 0.002, "kg"), _m(0.5, 0.001, "kg"), _m(9.80665, 0.0, "m/s^2"))
    area = cross_area(_m(0.006, 0.00002, "m"))
    if isinstance(force, Err) or isinstance(area, Err):
        _log.warning("nominal budgets: force/area failed")
        return []
    f, a = force.danger_ok, area.danger_ok
    cases = [
        ("stress", "Stress", stress, (f, a)),
        (
            "E",
            "Young's modulus (chord)",
            chord_modulus,
            (
                _m(5.0e6, 5.0e4, "Pa"),
                _m(5.0e7, 5.0e5, "Pa"),
                _m(1e-5, 1e-7, "1"),
                _m(1e-4, 1e-6, "1"),
            ),
        ),
    ]
    out: list[LabBudget] = []
    for result, label, fn, args in cases:
        bud = fn.budget(*args)
        ltx = fn.latex
        if isinstance(bud, Err) or isinstance(ltx, Err):
            _log.warning("nominal budget %s unavailable", result)
            continue
        out.append(LabBudget(result=result, label=label, budget=bud.danger_ok, latex=ltx.danger_ok))
    _log.debug("nominal budgets: %d built", len(out))
    return out
