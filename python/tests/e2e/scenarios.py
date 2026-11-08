"""The e2e scenario matrix: short simulator scenarios, one per fault family plus a combined run."""

# frob:ticket 01M6W7RB61AEQRD899AWKK27QJ
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tests.e2e.harness import ByteDrop

DURATION_S = 0.6
LOAD_AT_S = 0.1
MASS_KG = 1.0
# Noise grid of the simulator's fault model; analysis decimation matches it (see harness).
NOISE_GRID_HZ = 2000.0


# The simulator injects default noise and creep when a plan omits them; start every row quiet.
QUIET: dict[str, Any] = {
    "seed": 3,
    "sample_rate_hz": NOISE_GRID_HZ,
    "noise": {"sd_v": 0.0, "kind": {"kind": "white"}},
    "creep": {"coeff": 0.0, "tau_s": 0.01},
}


@dataclass(frozen=True)
class Spec:
    """One matrix row: simulator fault plan plus byte drops and the expectations to assert."""

    name: str
    faults: dict[str, Any] = field(default_factory=dict)
    drops: tuple[ByteDrop, ...] = ()


def scenario_dict(spec: Spec) -> dict[str, Any]:
    """Build the simulator scenario JSON-dict for `spec` (one 1 kg step at LOAD_AT_S)."""
    faults = {**QUIET, **spec.faults}
    return {
        "name": f"e2e-{spec.name}",
        "description": f"e2e fault scenario {spec.name}",
        "load": {"steps": [{"t_s": LOAD_AT_S, "mass_kg": MASS_KG}]},
        "faults": faults,
    }


NOISE_SD_V = 0.002
DRIFT_V_PER_S = 3.0
CREEP_COEFF = 0.5
CREEP_TAU_S = 0.01
SLIP_T_S = 0.4
SLIP_STRAIN = 0.005
CLAMP_V = 1.005
COMBINED_CLAMP_V = 1.1

NOISE = Spec("noise", {"noise": {"sd_v": NOISE_SD_V, "kind": {"kind": "white"}}})
DRIFT = Spec("drift", {"drift": {"linear_v_per_s": DRIFT_V_PER_S}})
CREEP = Spec("creep", {"creep": {"coeff": CREEP_COEFF, "tau_s": CREEP_TAU_S}})
SLIP = Spec("slip", {"slips": [{"t_s": SLIP_T_S, "strain": SLIP_STRAIN}]})
DROPPED = Spec("dropped", drops=(ByteDrop(block=3, count=100), ByteDrop(block=9, count=37)))
SATURATION = Spec("saturation", {"saturation": {"limit_v": CLAMP_V, "mode": "clamp"}})
COMBINED = Spec(
    "combined",
    {
        "noise": {"sd_v": NOISE_SD_V, "kind": {"kind": "white"}},
        "creep": {"coeff": CREEP_COEFF, "tau_s": CREEP_TAU_S},
        "slips": [{"t_s": SLIP_T_S, "strain": SLIP_STRAIN}],
        "saturation": {"limit_v": COMBINED_CLAMP_V, "mode": "clamp"},
    },
    drops=(ByteDrop(block=5, count=61),),
)
BASELINE = Spec("baseline")
MATRIX = (NOISE, DRIFT, CREEP, SLIP, DROPPED, SATURATION, COMBINED)
