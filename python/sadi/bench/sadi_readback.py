"""Read injected levels back from a real SADI board over the serial facade (core phases)."""

# frob:ticket 01M6Z3095E9TR8FEQM7Y6MM2ZP
from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.bench.lctt_source import BOARD_FULL_SCALE_V, AdcModel
from sadi.core.devfacade import default_adc_mode
from sadi.core.errors import DeviceCode, DeviceError
from sadi.core.phases import open_serial
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

__all__ = ["BOARD_FULL_SCALE_V", "BoardReading", "board_adc_model", "read_board"]

_SETTLE_S = 0.3  # let the AD3 output settle before the stream starts
_DISCARD_BLOCKS = 8  # leading blocks that may straddle the stimulus step


class BoardReading(BaseModel):
    """Mean per-channel ADC result of one board read: volts and raw codes for ACH0..ACH3."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    volts: tuple[float, float, float, float]
    codes: tuple[float, float, float, float]
    n: int


def board_adc_model() -> AdcModel:
    """The `AdcModel` matching the real board's +-5.12 V range (also the `AdcModel` default)."""
    return AdcModel(full_scale_v=BOARD_FULL_SCALE_V)


@dataclass
class _Cols:
    """Accumulated volts and raw-code columns."""

    volts: list[NDArray[np.float64]]
    codes: list[NDArray[np.float64]]

    def n(self) -> int:
        """Samples collected so far."""
        return sum(len(v) for v in self.volts)


def read_board(port: str, n: int = 400) -> Result[BoardReading, DeviceError]:
    """Stream `n` samples from the SADI at `port` (fresh session) and return their mean.

    Call after the stimulus is applied; the session is always stopped and closed.
    """
    time.sleep(_SETTLE_S)
    opened = open_serial(port)
    if isinstance(opened, Err):
        return Err(opened.danger_err)
    conn = opened.danger_ok.connect()
    if isinstance(conn, Err):
        _log.error("sadi connect failed on %s: %s", port, conn.danger_err.detail)
        opened.danger_ok.close()
        return Err(conn.danger_err)
    mode = default_adc_mode()
    if isinstance(mode, Err):
        conn.danger_ok.close()
        return Err(mode.danger_err)
    started = conn.danger_ok.start(mode.danger_ok)
    if isinstance(started, Err):
        conn.danger_ok.close()
        return Err(started.danger_err)
    streaming = started.danger_ok
    cols = _Cols([], [])
    result: Result[BoardReading, DeviceError] = Err(
        DeviceError(code=DeviceCode.TIMEOUT, detail="no samples collected")
    )
    for i in range(_DISCARD_BLOCKS + 1000):
        blk = streaming.read_block()
        if isinstance(blk, Err):
            result = Err(blk.danger_err)
            break
        if i < _DISCARD_BLOCKS:
            continue
        cols.volts.append(np.asarray(blk.danger_ok.volts, dtype=np.float64))
        cols.codes.append(np.asarray(blk.danger_ok.adc_raw, dtype=np.float64))
        if cols.n() >= n:
            v = np.concatenate(cols.volts).mean(axis=0)
            c = np.concatenate(cols.codes).mean(axis=0)
            result = Ok(
                BoardReading(
                    volts=(float(v[0]), float(v[1]), float(v[2]), float(v[3])),
                    codes=(float(c[0]), float(c[1]), float(c[2]), float(c[3])),
                    n=cols.n(),
                )
            )
            break
    stopped = streaming.stop()
    if isinstance(stopped, Ok):
        closed = stopped.danger_ok[0].close()
    else:
        closed = streaming.force_close()
    _log.info("sadi board read done ok=%s close_ok=%s", result.is_ok, closed.is_ok)
    return result
