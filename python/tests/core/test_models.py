"""Tests for sadi.core.models and sadi.core.errors."""

from __future__ import annotations

import math

import pytest
from pydantic import ValidationError
from typani import Err

from sadi.core import errors as E
from sadi.core.models import (
    CapturedPoint,
    Phase,
    PointEdit,
    Quantity,
    RunState,
    SettleStatus,
    Specimen,
    TimeWindow,
)

TICKET = "01M6W7R13KW0FFYHZJ7FY28A3R"


def _specimen() -> Specimen:
    return Specimen(
        id="s1",
        l0=Quantity(value=0.08313, standard_uncertainty=0.0005, unit="m"),
        diameter=Quantity(value=2.019e-4, standard_uncertainty=2.5e-6, unit="m"),
    )


def _point(i: int = 0, status: SettleStatus = SettleStatus.SETTLED) -> CapturedPoint:
    return CapturedPoint(
        index=i,
        window=TimeWindow(start=1.0, end=6.0),
        t_since_load=12.5,
        drift_rate=-1e-5,
        status=status,
        edits=(PointEdit(field="window", old="1-6", new="2-6", at=30.0),),
    )


# frob:ticket 01M6W7R13KW0FFYHZJ7FY28A3R
def test_json_round_trip_all_models() -> None:
    """Every model survives model_dump_json / model_validate_json unchanged."""
    state = RunState(
        session_id="abc",
        phase=Phase.ELASTIC,
        specimen=_specimen(),
        tare=Quantity(value=0.01, standard_uncertainty=0.001, unit="V"),
        points=(_point(0), _point(1, SettleStatus.FORCED_EARLY)),
    )
    for obj in (state, _specimen(), _point()):
        assert type(obj).model_validate_json(obj.model_dump_json()) == obj


# frob:ticket 01M6W7R13KW0FFYHZJ7FY28A3R
def test_quantity_rejects_bad_input() -> None:
    """Non-SI units, negative uncertainty and NaN are refused."""
    with pytest.raises(ValidationError):
        Quantity(value=1.0, unit="mm")
    with pytest.raises(ValidationError):
        Quantity(value=1.0, standard_uncertainty=-1.0)
    with pytest.raises(ValidationError):
        Quantity(value=math.nan)


# frob:ticket 01M6W7R13KW0FFYHZJ7FY28A3R
# frob:tests python/sadi/core/models.py::Specimen.area
def test_specimen_area_and_validation() -> None:
    """Area matches pi d^2 / 4 (3.2016e-8 m^2) and non-metre lengths are refused."""
    a = _specimen().area
    assert a.unit == "m^2"
    assert a.value == pytest.approx(3.2016e-8, rel=1e-4)
    with pytest.raises(ValidationError):
        Specimen(id="x", l0=Quantity(value=1.0, unit="kg"), diameter=Quantity(value=1.0, unit="m"))


# frob:ticket 01M6W7R13KW0FFYHZJ7FY28A3R
# frob:tests python/sadi/core/models.py::CapturedPoint.settled
# frob:tests python/sadi/core/models.py::CapturedPoint.forced_early
def test_point_flags_window_and_run_state_transitions() -> None:
    """settled/forced_early flags, window ordering, and immutable state updates."""
    assert _point().settled and not _point().forced_early
    assert _point(status=SettleStatus.FORCED_EARLY).forced_early
    with pytest.raises(ValidationError):
        TimeWindow(start=5.0, end=1.0)
    s0 = RunState(session_id="s")
    s1 = s0.advance(Phase.PLASTIC).with_point(_point())
    assert s0.phase is Phase.CALIBRATION and not s0.points
    assert s1.phase is Phase.PLASTIC and len(s1.points) == 1


def test_phase_has_tare_results_export() -> None:
    """Tare, results and export are distinct phases whose values match WAL phase names."""
    assert [p.value for p in Phase] == [
        "setup", "calibration", "tare", "elastic", "plastic", "results", "export"
    ]  # fmt: skip


# frob:ticket 01M6W7R13KW0FFYHZJ7FY28A3R
# frob:tests python/sadi/core/errors.py::hint_for
# frob:tests python/sadi/core/errors.py::SadiError.hint
# frob:tests python/sadi/core/errors.py::SadiError.status
def test_every_error_code_has_hint_and_problem_json() -> None:
    """Each code of each family carries a non-empty hint and a 7807 body."""
    enums = {
        E.DeviceError: E.DeviceCode,
        E.InputError: E.InputCode,
        E.StoreError: E.StoreCode,
        E.ComputeError: E.ComputeCode,
        E.JobError: E.JobCode,
    }
    assert set(enums) == set(E.ERROR_TYPES)
    for cls, codes in enums.items():
        for code in codes:
            err = cls(code=code, detail="d")
            assert err.hint == E.hint_for(code)
            body = err.problem()
            assert body["hint"] == err.hint
            assert body["status"] == err.status
            assert str(body["type"]).startswith(f"urn:sadi:error:{cls.family}:")
            assert cls.model_validate_json(err.model_dump_json()) == err


# frob:ticket 01M6W7R13KW0FFYHZJ7FY28A3R
def test_errors_are_frozen_and_usable_in_result() -> None:
    """Errors are immutable values and work as the E of a Result."""
    err = E.DeviceError(code=E.DeviceCode.TIMEOUT)
    with pytest.raises(ValidationError):
        err.detail = "x"  # ty: ignore[invalid-assignment]
    assert Err(err).danger_err is err


# frob:ticket 01M6WBKXD1562WNR2FQS9RXHNM
# frob:tests python/sadi/core/errors.py::StoreCode
def test_store_code_covers_writer_failures() -> None:
    """StoreCode carries the writer-thread failures, each with a hint and a 500 body."""
    for name in ("backpressure", "disk_full", "closed", "stalled"):
        err = E.StoreError(code=E.code_from_wire(E.StoreCode, name))
        assert err.hint
        assert err.problem()["type"] == f"urn:sadi:error:store:{name}"
        assert err.status == 500


# frob:ticket 01M6WK3STJ55FH80KFAPYEFC79
# frob:tests python/sadi/core/errors.py::wire
def test_error_codes_are_error_sets_with_stable_wire_values() -> None:
    """Every code family is an ErrorSet; wire values stay the legacy lowercase strings."""
    from typani import ErrorSet

    for fam in (E.DeviceCode, E.InputCode, E.StoreCode, E.ComputeCode, E.JobCode):
        assert issubclass(fam, ErrorSet)
        for code in fam:
            assert E.code_from_wire(fam, E.wire(code)) is code
            assert E.hint_for(code)
    assert E.wire(E.StoreCode.DISK_FULL) == "disk_full"
    assert E.wire(E.JobCode.WORKER_CRASHED) == "worker_crashed"


# frob:ticket 01M6WK3STJ55FH80KFAPYEFC79
# frob:tests python/sadi/store/writer_thread.py::WriterError
def test_writer_errors_map_to_store_codes() -> None:
    """Each writer failure carries a StoreCode and converts to a StoreError."""
    from sadi.store import writer_thread as W

    assert W.Closed().code is E.StoreCode.CLOSED
    assert W.IoError(reason="x").to_store_error().code is E.StoreCode.IO
    assert W.DiskFull(reason="x").to_store_error("d").detail == "d"
