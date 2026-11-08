"""Typed stubs for sadi_py.sim: scenario/fault-plan validation and live control."""

from typing import Any, Mapping, Sequence

from sadi_py import Session, SessionConfig

JsonLike = str | Mapping[str, Any]

class SimControl:
    """Thread-safe live handle on a running simulator's scenario."""
    @property
    def now_s(self) -> float:
        """Simulated seconds the device last sampled."""
    @property
    def mass_kg(self) -> float:
        """Hanging mass in kg at the current simulated time."""
    @property
    def slip_count(self) -> int:
        """Number of slip steps configured or injected."""
    @property
    def seed(self) -> int:
        """Current noise seed."""
    def set_scenario(self, scenario: JsonLike) -> None:
        """Replace the scenario (builtin name, JSON text or dict); ScenarioFailure if invalid."""
    def set_fault_plan(self, plan: JsonLike) -> None:
        """Replace the fault plan (JSON text or dict); ScenarioFailure if invalid."""
    def set_load_program(self, steps: Sequence[tuple[float, float]]) -> None:
        """Replace the load program with (t_s, mass_kg) steps; ScenarioFailure if unordered."""
    def add_weight(self, kg: float) -> float:
        """Add hanging mass now; returns the new total mass."""
    def remove_weight(self, kg: float) -> float:
        """Remove hanging mass now; returns the new total mass."""
    def inject_slip(self, strain: float) -> float:
        """Inject a slip step now; returns the sim time it took effect."""
    def set_seed(self, seed: int) -> None:
        """Reseed the noise generator."""

def open(
    scenario: JsonLike,
    seed: int | None = None,
    cfg: SessionConfig | None = None,
    byte_faults: JsonLike | None = None,
) -> tuple[Session, SimControl]:
    """Open a simulator session plus its runtime control handle.

    `byte_faults` is a ByteFaultPlan (JSON text or dict) injecting seeded wire faults.
    """
def validate_scenario(scenario: JsonLike) -> None:
    """Raise ScenarioFailure unless the scenario (name, JSON text or dict) is valid."""
def validate_fault_plan(plan: JsonLike) -> None:
    """Raise ScenarioFailure unless the fault plan (JSON text or dict) is valid."""
def validate_byte_fault_plan(plan: JsonLike) -> None:
    """Raise ScenarioFailure unless the byte-fault plan (JSON text or dict) is valid.

    Keys: seed (int) and per-byte drop, duplicate, flip plus per-read truncate, stall,
    short_read probabilities in [0, 1]; unknown keys are rejected.
    """
