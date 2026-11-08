"""Guard: doctor and server failure families are typani ErrorSets, labels stay StrEnum."""

from __future__ import annotations

from enum import StrEnum

from typani import ErrorSet

from sadi.doctor import schema
from sadi.server.routes_stress_strain import RefitError


# frob:ticket 01M6WN9ZE5EHGWZZ58M973FKGT
def test_error_families_are_errorsets() -> None:
    """DoctorError and RefitError are ErrorSets, not StrEnums."""
    for fam in (schema.DoctorError, RefitError):
        assert issubclass(fam, ErrorSet)
        assert not issubclass(fam, StrEnum)


# frob:ticket 01M6WN9ZE5EHGWZZ58M973FKGT
def test_state_enums_stay_strenum() -> None:
    """Status and label enums keep their string wire values."""
    for enum in (schema.Layer, schema.Severity, schema.Status, schema.SkipReason):
        assert issubclass(enum, StrEnum)
    assert schema.Status.PASS == "pass"
    assert schema.SkipReason.PORT_BUSY == "port-busy"
