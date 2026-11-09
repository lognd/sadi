"""Typed constants transcribed from the Digilent dwf.h header (header not vendored)."""

# frob:ticket 01M6WSPW5XB6P5V3PR5SHEH6FP
# frob:ticket 01M6Z3092SGKVHQ3CZ98AMGV5D
from __future__ import annotations

from enum import IntEnum, IntFlag
from typing import Final, NewType

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

# Environment variable that overrides library discovery with an explicit path.
ENV_LIB_PATH: Final = "SADI_DWF_LIB"

# Buffer sizes from the C API (szError[512], szVersion[32], szDeviceName[32], szSN[32]).
ERROR_MSG_LEN: Final = 512
VERSION_LEN: Final = 32
NAME_LEN: Final = 32

# HDWF value meaning "no device" (hdwfNone).
HDWF_NONE: Final = 0
# FDwfDeviceOpen index meaning "first available device".
FIRST_DEVICE: Final = -1

# Sanity ceilings validated before the FFI call (the library enforces the real device limits).
MAX_CHANNELS: Final = 16
MAX_NODES: Final = 16
MAX_DEVICES: Final = 64
MAX_BUFFER_SAMPLES: Final = 1 << 22
INT_MIN: Final = -(1 << 31)
INT_MAX: Final = (1 << 31) - 1
UINT_MAX: Final = (1 << 32) - 1

Channel = NewType("Channel", int)
"""Zero-based instrument channel index (idxChannel)."""

IoNode = NewType("IoNode", int)
"""Zero-based node index within an analog IO channel (idxNode)."""


class EnumFilter(IntFlag):
    """Device enumeration filter (ENUMFILTER)."""

    ALL = 0
    USB = 0x0000001
    NETWORK = 0x0000002
    AXI = 0x0000004
    REMOTE = 0x1000000
    AUDIO = 0x2000000
    DEMO = 0x4000000


class DeviceId(IntEnum):
    """Digilent device family id (DEVID) reported by enumeration."""

    EEXPLORER = 1
    DISCOVERY = 2
    DISCOVERY2 = 3
    DDISCOVERY = 4
    ADP3X50 = 6
    ECLYPSE = 7
    ADP5250 = 8
    DPS3340 = 9
    DISCOVERY3 = 10
    ADP5470 = 11
    ADP5490 = 12
    ADP2230 = 14
    ADSMAX = 15


class AcqState(IntEnum):
    """Instrument state (DwfState) returned by the status calls."""

    READY = 0
    ARMED = 1
    DONE = 2
    TRIGGERED = 3  # same value as running in the header
    CONFIG = 4
    PREFILL = 5
    NOT_DONE = 6
    WAIT = 7


class AcqMode(IntEnum):
    """Analog in acquisition mode (ACQMODE)."""

    SINGLE = 0
    SCAN_SHIFT = 1
    SCAN_SCREEN = 2
    RECORD = 3
    OVERSAMPLE = 4
    SINGLE1 = 5


class WaveFunction(IntEnum):
    """Analog out waveform (FUNC)."""

    DC = 0
    SINE = 1
    SQUARE = 2
    TRIANGLE = 3
    RAMP_UP = 4
    RAMP_DOWN = 5
    NOISE = 6
    PULSE = 7
    TRAPEZIUM = 8
    SINE_POWER = 9


class OutNode(IntEnum):
    """Analog out node of a channel (AnalogOutNode)."""

    CARRIER = 0
    FM = 1
    AM = 2


class DwfParam(IntEnum):
    """Library parameter id (DwfParam) for the subset SADI uses."""

    ON_CLOSE = 4  # value 0 continue, 1 stop, 2 shutdown


class DwfErc(IntEnum):
    """Last-error code (DWFERC) from FDwfGetLastError."""

    NO_ERC = 0
    UNKNOWN_ERROR = 1
    API_LOCK_TIMEOUT = 2
    ALREADY_OPENED = 3
    NOT_SUPPORTED = 4
    INVALID_PARAMETER0 = 0x10
    INVALID_PARAMETER1 = 0x11
    INVALID_PARAMETER2 = 0x12
    INVALID_PARAMETER3 = 0x13
    INVALID_PARAMETER4 = 0x14


_log.debug("ad3 constants loaded")
