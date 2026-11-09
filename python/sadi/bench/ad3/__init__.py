"""Typed binding for the Digilent Analog Discovery 3 (DWF); importing never touches the library."""

# frob:ticket 01M6WSPW5XB6P5V3PR5SHEH6FP
from __future__ import annotations

from sadi.bench.ad3.backend import (
    ClosedDevice,
    DeviceInfo,
    DwfBackend,
    DwfCode,
    DwfError,
    OpenDevice,
)
from sadi.bench.ad3.consts import (
    AcqMode,
    AcqState,
    Channel,
    DeviceId,
    IoNode,
    OutNode,
    WaveFunction,
)
from sadi.bench.ad3.device import Ad3Closed, Ad3Session, open_ad3
from sadi.bench.ad3.dll import CtypesBackend, load_backend, load_library

__all__ = [
    "Ad3Closed",
    "Ad3Session",
    "AcqMode",
    "AcqState",
    "Channel",
    "ClosedDevice",
    "CtypesBackend",
    "DeviceId",
    "DeviceInfo",
    "DwfBackend",
    "DwfCode",
    "DwfError",
    "IoNode",
    "OpenDevice",
    "OutNode",
    "WaveFunction",
    "load_backend",
    "load_library",
    "open_ad3",
]
