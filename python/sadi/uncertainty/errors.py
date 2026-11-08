"""Typed error enum for the uncertainty package; every member carries a what-to-do hint."""

# frob:ticket 01M6W7R155JD0XGVXHDSP19B1H

from __future__ import annotations

from typani import ErrorSet


class UncertaintyError(ErrorSet):
    """Failure modes of the uncertainty engine; the description says what to do next."""

    UnknownUnit = "Unit string is not recognised; use a pint unit such as 'm', 'kg' or 'N/m**2'"
    DimensionMismatch = "Operands have different dimensions; convert to compatible units first"
    InvalidValue = "Value must be finite; check the measurement source for NaN or inf"
    InvalidUncertainty = "Standard uncertainty must be finite and >= 0; check the instrument spec"
    InvalidCorrelation = "Correlation must lie in [-1, 1]; recompute it from the covariance"
    InvalidDof = "Degrees of freedom must be > 0 (use None or inf for a Type B / exact input)"
    InvalidExponent = "Exponent must be a finite real number; use a dimensionless scalar"
    DomainError = "Operation is undefined here (division by zero or non-real result); change inputs"
    ZeroValue = "Relative uncertainty needs a non-zero value; use the absolute uncertainty instead"
    NoContributions = "No uncertainty contributions given; pass at least one (u_i, dof_i) pair"
    BadJson = "JSON does not describe a Measured; re-export it from a current SADI version"


def hint(error: UncertaintyError) -> str:
    """Return the human-readable what-to-do hint for `error`."""
    return error.description
