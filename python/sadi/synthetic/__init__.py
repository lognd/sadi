"""Opt-in simulated copper specimen: physics, scenario generator, device and headless driver."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from sadi.synthetic.confirm import EnableError, check_enable
from sadi.synthetic.provenance import CONFIRM_PHRASE, REAL, SYNTHETIC, DataProvenance

__all__ = [
    "CONFIRM_PHRASE",
    "REAL",
    "SYNTHETIC",
    "DataProvenance",
    "EnableError",
    "check_enable",
]
