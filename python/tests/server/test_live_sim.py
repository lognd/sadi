"""Simulated calibrate marks move the LVDT voltage; load steps follow the panel masses."""

# frob:ticket 01M72ZNB9TN1CWMCK5G1J1H0BX
from __future__ import annotations

from typing import Any

import pytest
from typani import Ok

from sadi.core.pipeline import Bus
from sadi.labs.lctt.guidance import Phase
from sadi.server.live import SIM_CAL_STEP_KG, SIM_LOAD_STEP_KG, SIM_LOAD_TARGETS_KG, LiveAcquisition


class _SimDevice:
    """Tracks cumulative simulated mass."""

    is_simulator = True

    def __init__(self) -> None:
        self.total = 0.0
        self.totals: list[float] = []

    def sim_add_weight(self, kg: float) -> Any:
        self.total = round(self.total + kg, 6)
        self.totals.append(self.total)
        return Ok(self.total)


def _live(dev: _SimDevice, phase: Phase) -> LiveAcquisition:
    live = LiveAcquisition(dev, Bus(), watch_poll_s=3600.0)  # type: ignore[arg-type]
    live.set_phase_source(lambda: phase)
    return live


# frob:tests python/sadi/server/live.py::LiveAcquisition._apply_sim_load
def test_calibrate_marks_give_distinct_synthetic_mass() -> None:
    dev = _SimDevice()
    live = _live(dev, Phase.CALIBRATE)
    for _ in range(3):
        live._apply_sim_load()
    assert dev.totals == pytest.approx([SIM_CAL_STEP_KG * k for k in (1, 2, 3)])
    assert len(set(dev.totals)) == 3


# frob:tests python/sadi/server/live.py::LiveAcquisition._next_sim_step
def test_load_steps_follow_panel_masses() -> None:
    dev = _SimDevice()
    live = _live(dev, Phase.ELASTIC)
    for _ in SIM_LOAD_TARGETS_KG:
        live._apply_sim_load()
    assert dev.totals == pytest.approx(list(SIM_LOAD_TARGETS_KG))
    assert SIM_LOAD_TARGETS_KG == (0.075, 1.05, 2.325)
    assert SIM_LOAD_STEP_KG == 0.075
