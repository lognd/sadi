"""Tests for sadi_py.sim: scenario/fault-plan validation and runtime control."""

import json
import threading

import pytest

import sadi_py as sp
from sadi_py import sim


def _stream():
    s, ctl = sim.open("clean", 1)
    s.connect()
    s.start(sp.AdcMode.DLL_COMPATIBLE)
    return s, ctl


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::validate_scenario
def test_validate_scenario_accepts_name_json_and_dict() -> None:
    sim.validate_scenario("clean")
    sim.validate_scenario(json.dumps({"name": "x"}))
    sim.validate_scenario({"name": "x", "load": {"steps": [{"t_s": 0.0, "mass_kg": 1.0}]}})


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::validate_scenario
def test_invalid_scenario_is_typed_error() -> None:
    with pytest.raises(sp.ScenarioFailure) as ei:
        sim.validate_scenario({"bogus": 1})
    assert ei.value.kind == "scenario"
    with pytest.raises(sp.ScenarioFailure):
        sim.validate_scenario("no-such-scenario")
    with pytest.raises(sp.ScenarioFailure):
        sim.validate_scenario(
            {"load": {"steps": [{"t_s": 2.0, "mass_kg": 1.0}, {"t_s": 1.0, "mass_kg": 2.0}]}}
        )


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::validate_fault_plan
def test_validate_fault_plan() -> None:
    sim.validate_fault_plan({"seed": 5, "slips": [{"t_s": 1.0, "strain": 1e-3}]})
    with pytest.raises(sp.ScenarioFailure) as ei:
        sim.validate_fault_plan({"noise": {"sd_v": -1.0}})
    assert ei.value.kind == "scenario"
    with pytest.raises(sp.ScenarioFailure):
        sim.validate_fault_plan("{not json")


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.set_fault_plan
def test_set_fault_plan_invalid_leaves_state() -> None:
    s, ctl = sim.open("clean", 3)
    with pytest.raises(sp.ScenarioFailure):
        ctl.set_fault_plan({"bogus": True})
    assert ctl.seed == 3
    ctl.set_fault_plan({"seed": 9})
    assert ctl.seed == 9
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.set_seed
def test_set_seed() -> None:
    s, ctl = sim.open("noisy", 1)
    ctl.set_seed(42)
    assert ctl.seed == 42
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.set_load_program
def test_set_load_program_validates() -> None:
    s, ctl = sim.open("clean", 1)
    ctl.set_load_program([(0.0, 1.0), (1.0, 2.0)])
    with pytest.raises(sp.ScenarioFailure):
        ctl.set_load_program([(1.0, 1.0), (0.5, 2.0)])
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.add_weight
# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.remove_weight
def test_add_and_remove_weight_while_streaming() -> None:
    s, ctl = _stream()
    ctl.set_load_program([])
    s.read_block()
    assert ctl.add_weight(0.5) == pytest.approx(0.5)
    assert ctl.mass_kg == pytest.approx(0.5)
    s.read_block()
    assert ctl.remove_weight(0.2) == pytest.approx(0.3)
    with pytest.raises(sp.ScenarioFailure):
        ctl.remove_weight(10.0)
    with pytest.raises(sp.ConfigurationError):
        ctl.add_weight(-1.0)
    s.stop()
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.inject_slip
def test_inject_slip_changes_signal() -> None:
    s, ctl = _stream()
    ctl.set_load_program([(0.0, 1.0)])
    before = s.read_block()
    n = ctl.slip_count
    ctl.inject_slip(5e-3)
    assert ctl.slip_count == n + 1
    after = s.read_block()
    assert before.volts[:, 0].mean() != after.volts[:, 0].mean()
    with pytest.raises(sp.ScenarioFailure):
        ctl.inject_slip(float("nan"))
    s.stop()
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.set_scenario
def test_set_scenario_swap() -> None:
    s, ctl = sim.open("clean", 1)
    ctl.set_scenario("noisy")
    with pytest.raises(sp.ScenarioFailure):
        ctl.set_scenario("nope")
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.set_seed
# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.inject_slip
def test_control_is_thread_safe() -> None:
    s, ctl = _stream()
    base = ctl.slip_count

    def work(i: int) -> None:
        for _ in range(50):
            ctl.set_seed(i)
            ctl.inject_slip(1e-7)

    threads = [threading.Thread(target=work, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
    for _ in range(5):
        s.read_block()
    for t in threads:
        t.join()
    assert ctl.slip_count == base + 200
    s.stop()
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.now_s
# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.mass_kg
# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.slip_count
# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::SimControl.seed
# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::open
def test_open_and_state_getters() -> None:
    s, ctl = _stream()
    s.read_block()
    assert ctl.seed == 1
    assert ctl.now_s > 0.0
    assert ctl.mass_kg >= 0.0
    assert ctl.slip_count >= 0
    s.stop()
    s.close()


# frob:tests crates/sadi-py/python/sadi_py/sim.pyi::open
def test_open_accepts_session_config() -> None:
    s, _ = sim.open("clean", 1, sp.SessionConfig(read_timeout_ms=500))
    s.connect()
    s.close()
