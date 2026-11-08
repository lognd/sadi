"""Tests for sadi.core.formatting."""

# frob:ticket 01M6W7R1HWQMSEX38TQM27Y4NY

from __future__ import annotations

import math
from decimal import Decimal

import pytest
from pydantic import ValidationError
from typani import Err, Ok

from sadi.core.errors import ComputeCode, InputCode
from sadi.core.formatting import (
    FormatConfig,
    Notation,
    format_quantity,
    format_result,
    plain_language_confidence,
    round_sig,
)
from sadi.core.models import Quantity

SCI = FormatConfig(notation=Notation.SCIENTIFIC)

CASES = [
    # (value, u, unit, expected)
    (0.0123456, 0.000456, "m", "12.3 +/- 0.46 mm"),
    (1.23456e11, 2.3e9, "Pa", "123 +/- 2.3 GPa"),
    (0.0, 0.0, "N", "0 +/- 0 N"),
    (0.0, 0.0123, "V", "0 +/- 12 mV"),
    (-0.0123456, 0.000456, "m", "-12.3 +/- 0.46 mm"),
    (-0.0, 0.0, "m", "0 +/- 0 m"),
    (5e-9, 1e-10, "m", "5.00 +/- 0.10 nm"),
    (3.2e-30, 1e-31, "m", "0.00000320 +/- 0.00000010 ym"),
    (1.5e30, 1e28, "Pa", "1500000 +/- 10000 YPa"),
    (0.5, 2.0, "m", "500 +/- 2000 mm"),
    (999.6, 0.0996, "m", "1.00 +/- 0.00010 km"),
    (1.0, 0.14, "m", "1.00 +/- 0.14 m"),
    (1.0, 0.0996, "m", "1.00 +/- 0.10 m"),
    (1.0, 0.1, "m", "1.00 +/- 0.10 m"),
    (2.675, 0.0, "m", "2.68 +/- 0 m"),
    (0.0831, 0.0004, "kg", "83.1 +/- 0.40 g"),
    (12345.0, 12.0, "1", "12300 +/- 12"),
    (2.5e7, 1e5, "1", "(25.0 +/- 0.10)e+6"),
    (1.2e-8, 1e-9, "m^2", "(12.0 +/- 1.0)e-9 m^2"),
    (0.01, 0.001, "m^2", "0.0100 +/- 0.0010 m^2"),
    (3.2016e-8, 1e-10, "m/V", "32.0 +/- 0.10 nm/V"),
]


@pytest.mark.parametrize(("value", "u", "unit", "expected"), CASES)
def test_format_result_table(value: float, u: float, unit: str, expected: str) -> None:
    # frob:tests python/sadi/core/formatting.py::format_result
    assert format_result(value, u, unit) == Ok(expected)


SCI_CASES = [
    (0.00123456, 0.000045, "m", "(1.23 +/- 0.045)e-3 m"),
    (123456.0, 120.0, "Pa", "(1.23 +/- 0.0012)e+5 Pa"),
    (0.0, 0.0, "m", "0 +/- 0 m"),
    (-4.0, 9.0, "V", "-4.00 +/- 9.0 V"),
    (0.0831, 0.0004, "kg", "(8.31 +/- 0.040)e-2 kg"),
]


@pytest.mark.parametrize(("value", "u", "unit", "expected"), SCI_CASES)
def test_format_result_scientific(value: float, u: float, unit: str, expected: str) -> None:
    # frob:tests python/sadi/core/formatting.py::format_result
    assert format_result(value, u, unit, SCI) == Ok(expected)


def test_configurable_sig_figs() -> None:
    # frob:tests python/sadi/core/formatting.py::FormatConfig
    cfg = FormatConfig(result_sf=4, uncertainty_sf=1)
    assert format_result(1.23456, 0.0456, "m", cfg) == Ok("1.235 +/- 0.05 m")


def test_config_rejects_bad_counts() -> None:
    # frob:tests python/sadi/core/formatting.py::FormatConfig
    with pytest.raises(ValidationError):
        FormatConfig(result_sf=0)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
def test_non_finite_is_err(bad: float) -> None:
    # frob:tests python/sadi/core/formatting.py::format_result
    for args in ((bad, 1.0), (1.0, bad)):
        r = format_result(*args)
        assert isinstance(r, Err)
        assert r.unwrap_err().code is ComputeCode.NOT_FINITE


def test_negative_uncertainty_is_err() -> None:
    # frob:tests python/sadi/core/formatting.py::format_result
    r = format_result(1.0, -0.1)
    assert isinstance(r, Err)
    assert r.unwrap_err().code is InputCode.OUT_OF_RANGE


def test_format_quantity() -> None:
    # frob:tests python/sadi/core/formatting.py::format_quantity
    q = Quantity(value=0.0123456, standard_uncertainty=0.000456, unit="m")
    assert format_quantity(q) == Ok("12.3 +/- 0.46 mm")


@pytest.mark.parametrize(
    ("x", "sf", "expected"),
    [("9.996", 3, "10.0"), ("0.0996", 2, "0.10"), ("123456", 3, "123000"), ("1.25", 2, "1.3")],
)
def test_round_sig(x: str, sf: int, expected: str) -> None:
    # frob:tests python/sadi/core/formatting.py::round_sig
    assert round_sig(Decimal(x), sf) == Decimal(expected)
    assert round_sig(Decimal(0), sf) == 0


CONF = [
    (100.0, 4.2, 0.05, "E is known to within 4.2 % at 95 % confidence; target 5 % reached"),
    (100.0, 6.0, 0.05, "E is known to within 6.0 % at 95 % confidence; target 5 % not reached"),
    (-100.0, 4.2, 0.05, "E is known to within 4.2 % at 95 % confidence; target 5 % reached"),
    (10.0, 25.0, 0.05, "E is known to within 250 % at 95 % confidence; target 5 % not reached"),
    (100.0, 5.04, 0.05, "E is known to within 5.0 % at 95 % confidence; target 5 % reached"),
    (100.0, 0.0, 0.05, "E is known to within 0 % at 95 % confidence; target 5 % reached"),
    (1e-12, 4e-14, 0.05, "E is known to within 4.0 % at 95 % confidence; target 5 % reached"),
    (1e12, 1e11, 0.025, "E is known to within 10 % at 95 % confidence; target 2.5 % not reached"),
]


@pytest.mark.parametrize(("value", "u", "target", "expected"), CONF)
def test_plain_language_confidence(value: float, u: float, target: float, expected: str) -> None:
    # frob:tests python/sadi/core/formatting.py::plain_language_confidence
    assert plain_language_confidence(value, u, target) == Ok(expected)


def test_confidence_errors() -> None:
    # frob:tests python/sadi/core/formatting.py::plain_language_confidence
    zero = plain_language_confidence(0.0, 1.0, 0.05)
    assert isinstance(zero, Err)
    assert zero.unwrap_err().code is ComputeCode.DEGENERATE
    nan = plain_language_confidence(math.nan, 1.0, 0.05)
    assert isinstance(nan, Err)
    assert nan.unwrap_err().code is ComputeCode.NOT_FINITE
    neg = plain_language_confidence(1.0, 0.1, 0.0)
    assert isinstance(neg, Err)
    assert neg.unwrap_err().code is InputCode.OUT_OF_RANGE


def test_confidence_label() -> None:
    # frob:tests python/sadi/core/formatting.py::plain_language_confidence
    r = plain_language_confidence(100.0, 1.0, 0.05, label="Yield stress")
    assert r == Ok("Yield stress is known to within 1.0 % at 95 % confidence; target 5 % reached")
