"""Open the real SADI board over serial for `sadi serve` (the non-sim, non-synthetic path)."""

# frob:ticket 01M71WYR7EH67QFSRH37QFCDAC
from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from typing import Final

from typani import Err, Ok, Result

from sadi.core.device import DeviceService, DeviceSource
from sadi.core.errors import DeviceError
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

#: Environment variable naming the serial port of the SADI board.
PORT_ENV: Final[str] = "SADI_PORT"
#: Default serial port on POSIX hosts (the FTDI bridge); other hosts auto-detect by FTDI id.
POSIX_DEFAULT_PORT: Final[str] = "/dev/ttyUSB0"


def resolve_device_port(flag: str | None, env: Mapping[str, str] | None = None) -> str | None:
    """Pick the serial port: the flag, else SADI_PORT, else /dev/ttyUSB0 on POSIX (None = auto-detect)."""
    values = os.environ if env is None else env
    chosen = flag or values.get(PORT_ENV, "").strip()
    if chosen:
        return chosen
    return POSIX_DEFAULT_PORT if sys.platform != "win32" else None


def describe_open_failure(err: DeviceError, port: str | None) -> str:
    """Plain-language one-paragraph explanation of why the board could not be opened."""
    where = port if port is not None else "any FTDI serial port"
    return (
        f"could not open the SADI board on {where}: {err.detail or err.code}. {err.hint} "
        "(Use --sim for the simulator, or --device-port / SADI_PORT to name the port.)"
    )


def open_real_device(port: str | None) -> Result[DeviceService, str]:
    """Open the SADI board on `port` as a streaming DeviceService; Err is a user-facing message."""
    svc = DeviceService(DeviceSource(kind="serial", port=port))
    opened = svc.open()
    if isinstance(opened, Err):
        _log.error("serial device open failed on %s: %s", port, opened.danger_err.detail)
        return Err(describe_open_failure(opened.danger_err, port))
    _log.info("serial device open on %s", port)
    return Ok(svc)
