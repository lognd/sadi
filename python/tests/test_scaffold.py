"""Smoke tests for the empty skeleton: imports, logger helper, typani non-shadowing."""

from __future__ import annotations

import importlib

import pytest

import sadi
from sadi.logging_setup import get_logger


# frob:ticket 01M6W7R0PMCGFDSFY53XDK2EVN
def test_packages_import() -> None:
    """Core and labs packages import."""
    assert sadi.__doc__ is not None and sadi.__doc__
    for mod in ("sadi.core", "sadi.labs", "sadi.logging_setup"):
        importlib.import_module(mod)


# frob:ticket 01M6W7R0PMCGFDSFY53XDK2EVN
def test_get_logger_routes_levels(capsys: pytest.CaptureFixture[str]) -> None:
    """INFO goes to stdout bare; WARNING goes to stderr with a level prefix."""
    log = get_logger("sadi.test")
    log.info("hello")
    log.warning("careful")
    cap = capsys.readouterr()
    assert "hello" in cap.out
    assert "WARNING: careful" in cap.err
    assert "careful" not in cap.out


# frob:ticket 01M6W7R0PMCGFDSFY53XDK2EVN
def test_typani_names_not_shadowed() -> None:
    """sadi must not define names that shadow typani's propagate/catching."""
    for name in ("propagate", "catching"):
        assert not hasattr(sadi, name)


# frob:ticket 01M6W7R0PMCGFDSFY53XDK2EVN
def test_get_logger_follows_stream_swap(capsys: pytest.CaptureFixture[str]) -> None:
    """Handlers must write to the live sys streams even when logging was initialized earlier."""
    get_logger("sadi.early")  # ensure handlers exist before this test's capture swap
    log = get_logger("sadi.late")
    log.info("to-out")
    log.warning("to-err")
    cap = capsys.readouterr()
    assert "to-out" in cap.out
    assert "WARNING: to-err" in cap.err
