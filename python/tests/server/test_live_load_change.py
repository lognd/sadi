"""The simulator hangs mass on a load-change mark only in the elastic and plastic phases."""

# frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
from __future__ import annotations

from typing import Any

import pytest
from typani import Ok

from sadi.core.pipeline import Bus
from sadi.labs.lctt.guidance import Phase
from sadi.server.live import SIM_LOAD_STEP_KG, LiveAcquisition


class _SimDevice:
    """Records simulated weight steps."""

    is_simulator = True

    def __init__(self) -> None:
        self.added: list[float] = []

    def sim_add_weight(self, kg: float) -> Any:
        self.added.append(kg)
        return Ok(None)


def _live(dev: _SimDevice) -> LiveAcquisition:
    return LiveAcquisition(dev, Bus(), watch_poll_s=3600.0)  # type: ignore[arg-type]


# frob:tests python/sadi/server/live.py::LiveAcquisition.set_phase_source
@pytest.mark.parametrize(
    ("phase", "steps"),
    [(None, 0), (Phase.ELASTIC, 1), (Phase.PLASTIC, 1)],
)
def test_sim_load_only_in_load_phases(phase: Phase | None, steps: int) -> None:
    dev = _SimDevice()
    live = _live(dev)
    live.set_phase_source(lambda: phase)
    live._apply_sim_load()
    assert dev.added == [SIM_LOAD_STEP_KG] * steps


# frob:tests python/sadi/server/live.py::LiveAcquisition.set_phase_source
def test_sim_load_without_phase_source_keeps_legacy_step() -> None:
    dev = _SimDevice()
    _live(dev)._apply_sim_load()
    assert dev.added == [SIM_LOAD_STEP_KG]
