"""Wizard.edit validates override_input against parse_inputs and check_ranges (audit5 MED 1)."""

# frob:ticket 01M72D3CTDED2MGDY721RSM8M4
from __future__ import annotations

import math

import pytest

from sadi.core.lab import CaptureKind, StepId, StepSpec
from sadi.core.models import Phase
from sadi.core.wizard import Wizard, WizardError
from sadi.store.events import PointV1, PointWindow, ReplayState, replay
from sadi.store.records import Record


def _setup() -> tuple[Wizard, ReplayState]:
    spec = StepSpec(
        id=StepId("calibrate"),
        title="Calibrate",
        phase=Phase.CALIBRATION,
        capture=CaptureKind.DEVICE_POINTS,
        guidance=lambda _r: "go",
    )
    w = Wizard.create([spec]).danger_ok
    pt = PointV1(
        point_id="p",
        phase="calibration",
        window=PointWindow(first_raw_seq=1, last_raw_seq=5),
        inputs={"volts": 1.0, "height": 0.01},
    )
    nr = w.capture(ReplayState(), pt).danger_ok.records[0]
    rec = Record(type=nr.type, seq=1, wall_ns=1, flags=nr.flags, payload=nr.payload, crc=0)
    return w, replay([rec]).danger_ok


# frob:tests python/sadi/core/wizard.py::Wizard.edit
@pytest.mark.parametrize(
    "args",
    [
        {"volts": "abc"},
        {"volts": float("nan")},
        {"volts": math.inf},
        {"volts": True},
        {"nope": 1.0},
        {"phase": "tare"},
        {"height": 5.0},  # metre-scale height: a unit slip
    ],
)
def test_override_input_rejects_bad_values(args: dict[str, object]) -> None:
    w, state = _setup()
    res = w.edit(state, "p", "override_input", args)
    assert res.danger_err is WizardError.BadInput


# frob:tests python/sadi/core/wizard.py::Wizard.edit
def test_override_input_accepts_valid_partial_override() -> None:
    w, state = _setup()
    res = w.edit(state, "p", "override_input", {"volts": 2.5})
    assert res.is_ok
