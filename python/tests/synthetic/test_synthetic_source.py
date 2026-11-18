"""The synthetic source: physics, determinism, opt-in gate, and the scenario generator."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

import numpy as np
import pytest

from sadi.synthetic.confirm import EnableError, check_enable
from sadi.synthetic.device import SyntheticDevice
from sadi.synthetic.provenance import CONFIRM_PHRASE
from sadi.synthetic.scenario import (
    TOL_E,
    TOL_YIELD,
    ScenarioFlags,
    generate_scenario,
)
from sadi.synthetic.specimen import CopperSpec


def _blocks(seed: int, kg: float, n: int = 3) -> np.ndarray:
    dev = SyntheticDevice(seed=seed, realtime=False)
    assert dev.open().is_ok
    dev.sim_add_weight(kg)
    assert dev.start_streaming().is_ok
    out = []
    for _ in range(n):
        got = dev.next_block()
        assert got.is_ok and got.danger_ok is not None
        out.append(got.danger_ok.volts)
    dev.close()
    return np.concatenate(out)


# frob:tests python/sadi/synthetic/device.py::SyntheticDevice._make_block
def test_device_is_deterministic_per_seed() -> None:
    """Same seed gives identical volts; a different seed differs."""
    a, b, c = _blocks(7, 0.2), _blocks(7, 0.2), _blocks(8, 0.2)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


# frob:tests python/sadi/synthetic/device.py::SyntheticDevice._make_block
def test_load_cell_tracks_load_and_lvdt_shows_creep() -> None:
    """More mass raises the load volts; LVDT volts keep rising while a load is held."""
    light, heavy = _blocks(1, 0.05), _blocks(1, 0.3)
    assert heavy[:, 2].mean() > light[:, 2].mean()
    held = _blocks(1, 0.3, n=12)
    first = held[:1250, 0].mean()
    last = held[-1250:, 0].mean()
    assert last > first


# frob:tests python/sadi/synthetic/specimen.py::CopperSpec
def test_spec_has_elastic_yield_hardening_and_creep() -> None:
    """Elastic slope is E, plastic strain appears past onset, stress saturates, creep grows."""
    s = CopperSpec()
    assert s.strain(30e6, 30e6) == pytest.approx(30e6 / s.e_pa, rel=1e-6)
    assert s.plastic_strain(100e6) > s.plastic_strain(70e6) > 0
    assert s.creep_strain(80e6, 60.0) > s.creep_strain(80e6, 1.0) > 0
    assert 80e9 < s.e_pa < 140e9 and 40e6 < s.onset_pa < 120e6


# frob:tests python/sadi/synthetic/scenario.py::generate_scenario
def test_scenario_is_seeded_and_truth_is_plausible_copper() -> None:
    """Same seed, same scenario; ground truth lies in a plausible Cu range."""
    a, b = generate_scenario(11), generate_scenario(11)
    assert a.model_dump() == b.model_dump()
    assert generate_scenario(12).model_dump() != a.model_dump()
    assert 80e9 < a.truth.e_pa < 140e9
    assert 30e6 < a.truth.yield_pa < 150e6


# frob:tests python/sadi/synthetic/scenario.py::generate_scenario
def test_scenario_variants() -> None:
    """Slip toggles setup slip events; duplicates and faults appear only when asked."""
    clean = generate_scenario(3, ScenarioFlags(slip=False))
    slipped = generate_scenario(3, ScenarioFlags(slip=True))
    assert sum(c.slip_events for c in clean.setup) == 0
    assert sum(c.slip_events for c in slipped.setup) > 0
    assert slipped.truth.slip and not clean.truth.slip
    assert clean.truth.faults == ()
    flagged = generate_scenario(3, ScenarioFlags(spike=True, saturation=True, dropped_frames=True))
    assert set(flagged.truth.faults) == {"spike", "saturation", "dropped_frames"}
    plain = generate_scenario(3, ScenarioFlags(duplicates=False, out_of_order=False))
    masses = [p.nominal_kg for p in plain.elastic]
    assert masses == sorted(masses) and len(set(masses)) == len(masses)
    assert TOL_E > 0 and TOL_YIELD > 0


# frob:tests python/sadi/synthetic/confirm.py::check_enable
def test_enable_needs_flag_and_exact_phrase() -> None:
    """Only flag plus the exact phrase enables; half-given or wrong input is refused."""
    assert check_enable(False, None).danger_ok is False
    assert check_enable(True, CONFIRM_PHRASE).danger_ok is True
    assert check_enable(True, None).danger_err == EnableError.NoPhrase
    assert check_enable(True, "yes").danger_err == EnableError.WrongPhrase
    assert check_enable(True, CONFIRM_PHRASE.lower()).is_err
    assert check_enable(False, CONFIRM_PHRASE).danger_err == EnableError.NoFlag


# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
# frob:tests python/sadi/synthetic/device.py::SyntheticDevice.fault
# frob:tests python/sadi/synthetic/device.py::SyntheticDevice.mass_kg
def test_device_reports_no_fault_and_tracks_mass() -> None:
    """The synthetic device never faults and mass_kg sums the hung weights."""
    dev = SyntheticDevice(seed=1, realtime=False)
    assert dev.open().is_ok
    assert dev.fault is None
    dev.sim_add_weight(0.25)
    dev.sim_add_weight(0.5)
    assert dev.mass_kg == pytest.approx(0.75)
    dev.close()


# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
# frob:tests python/sadi/synthetic/specimen.py::CopperSpec.area_m2
# frob:tests python/sadi/synthetic/specimen.py::CopperSpec.force_n
def test_spec_area_and_force_are_consistent() -> None:
    """force_n(stress) equals stress times the circular cross-section area."""
    spec = CopperSpec()
    assert spec.area_m2 == pytest.approx(3.2e-8, rel=0.01)
    assert spec.force_n(100e6) == pytest.approx(100e6 * spec.area_m2)
