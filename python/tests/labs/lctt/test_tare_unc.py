"""The reported tare quantity carries the standard error of the mean, sd/sqrt(n)."""

# frob:ticket 01M725CA43JK1ZDJKF8135RHT0

from __future__ import annotations

import math

from sadi.core.point_inputs import TareInputs
from sadi.labs.lctt.export_csv import tare_report
from sadi.labs.lctt.lab import LoadingContext, _calibration_quantities


# frob:tests python/sadi/labs/lctt/lab.py::_calibration_quantities
def test_tare_unc_is_standard_error() -> None:
    """sd=0.02 over n=100 samples gives 0.002 V, not the per-sample sd."""
    tare = TareInputs(mean=1.5, sd=0.02, n=100)
    ctx = LoadingContext(tare_v=tare.mean)
    q = _calibration_quantities([tare], ctx)["tare"]
    assert q.value == 1.5
    assert math.isclose(q.standard_uncertainty, 0.02 / math.sqrt(100))


def test_tare_unc_pools_all_blocks() -> None:
    """All tare blocks are pooled: Sx/sqrt(N), the same model the CSV reports."""
    a = TareInputs(mean=1.0, sd=0.5, n=4)
    b = TareInputs(mean=2.0, sd=0.3, n=9)
    q = _calibration_quantities([a, b], LoadingContext(tare_v=2.0))["tare"]
    want = tare_report([1.0, 2.0], [0.5, 0.3], [4, 9]).danger_ok
    assert math.isclose(q.standard_uncertainty, want.std_unc)
    assert math.isclose(q.value, want.value)
