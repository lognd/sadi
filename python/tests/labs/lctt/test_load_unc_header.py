"""Load-point voltage uncertainty from the server block, and operator/description in CSV headers."""

# frob:ticket 01M72YAG5JF05K4W68BCPGKVGP
# creates:python/tests/labs/lctt/test_load_unc_header.py

from __future__ import annotations

import math

from sadi.core.models import RunState
from sadi.labs.lctt.capture import RawBlockBuffer
from sadi.labs.lctt.lab import _write_csv_partial  # noqa: PLC2701
from sadi.labs.lctt.live import CalPoint
from sadi.server.schemas import CaptureBody, SessionCreate


def _svc(tmp_path):  # type: ignore[no-untyped-def]
    """Service with a session open past setup."""
    from sadi.core.registry import LabRegistry
    from sadi.labs.lctt.plugin import register
    from sadi.server.service import SessionService

    labs = LabRegistry()
    assert labs.register(register()).is_ok
    svc = SessionService(tmp_path, labs)
    assert svc.create(SessionCreate(lab="lctt", slug="u")).is_ok
    assert svc.skip("setup").is_ok
    return svc


# frob:tests python/sadi/server/service.py::SessionService._apply_block
def test_load_point_gets_block_sd_and_two_sd_uncertainty(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """A load capture stores block mean, sample sd and U_V = 2 sd, not the browser values."""
    svc = _svc(tmp_path)
    buf = RawBlockBuffer()
    buf.extend([2.0, 4.0] * 500)
    svc.set_block_source(buf.stats)
    try:
        body = CaptureBody.model_validate({
            "phase": "elastic",
            "inputs": {"volts": 9.0, "mass_kg": 0.5, "volts_sd": 7.0, "u_volts": 7.0},
            "window": {"first_raw_seq": 1, "last_raw_seq": 5},
        })
        inputs = svc._apply_block(body).unwrap()  # noqa: SLF001
        sd = buf.stats().unwrap().sd
        assert inputs["volts"] == 3.0
        assert math.isclose(inputs["volts_sd"], sd)
        assert math.isclose(inputs["u_volts"], 2.0 * sd)
    finally:
        svc.close()


# frob:tests python/sadi/labs/lctt/lab.py::_write_csv_partial
def test_csv_header_carries_operator_and_description() -> None:
    """RunState.meta operator/description reach the CSV metadata rows."""
    run = RunState(
        session_id="s",
        events=(CalPoint(volts=1.0, height=0.01), CalPoint(volts=2.0, height=0.02),
                CalPoint(volts=3.1, height=0.03)),
        meta={"operator": "Ada", "description": "cu wire 1"},
    )
    out = _write_csv_partial(run, None).unwrap()  # type: ignore[arg-type]
    text = out.decode()
    assert "Operator,Ada" in text
    assert "Description,cu wire 1" in text
