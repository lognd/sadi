"""LCTT plugin entry: the register() factory that contributes the lctt LabModule (see lab.py)."""

# frob:ticket 01M6WFZ1N70HDJJRZWRHWP4E7Y

from __future__ import annotations

from sadi.core.lab import LabModule
from sadi.labs.lctt.lab import LcttLab, setup_step
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = ["LcttLab", "register", "setup_step"]


def register() -> LabModule:
    """Plugin entry point: return the lctt LabModule."""
    _log.info("lctt plugin register")
    return LcttLab()
