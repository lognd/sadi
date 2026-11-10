"""Seeded generator of a whole simulated tensile lab: calibration, tare, slip check, two runs."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

from typing import Final

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

from sadi.logging_setup import get_logger
from sadi.synthetic.provenance import SYNTHETIC, DataProvenance
from sadi.synthetic.specimen import CopperSpec

_log = get_logger(__name__)

__all__ = [
    "CLAMP_CYCLES",
    "HANGER_KG",
    "LONG_L0_M",
    "N_PER_V",
    "SHORT_L0_M",
    "TOL_CAL_SLOPE",
    "TOL_E",
    "TOL_YIELD",
    "CalPoint",
    "PlannedPoint",
    "Scenario",
    "ScenarioFlags",
    "SetupCycle",
    "Tare",
    "Truth",
    "generate_scenario",
]

#: Gauge lengths (m); same constants the LCTT lab uses.
SHORT_L0_M: Final = 0.08313
LONG_L0_M: Final = 0.5
#: Hanger mass (kg) always on the specimen, and load-cell newtons per volt.
HANGER_KG: Final = 0.005
N_PER_V: Final = 2.0
G: Final = 9.80665
#: Clamp-check cycles the wizard needs.
CLAMP_CYCLES: Final = 3
#: Stated recovery tolerances (relative) between fitted values and ground truth.
TOL_E: Final = 0.06
TOL_YIELD: Final = 0.05
TOL_CAL_SLOPE: Final = 0.01
#: A hold is settled once the LVDT drift is below this (V/s).
DRIFT_SETTLED_V_PER_S: Final = 5e-6
_HOLD_GRID_S: Final = (2.0, 5.0, 10.0, 20.0, 40.0, 80.0, 160.0)
_N_WINDOW: Final = 1000
_FULL_SCALE_V: Final = 5.12


class ScenarioFlags(BaseModel):
    """Explicit switches for the lab variants; every fault is off unless asked for."""

    model_config = ConfigDict(frozen=True)

    slip: bool = False
    duplicates: bool = True
    out_of_order: bool = True
    dropped_frames: bool = False
    saturation: bool = False
    spike: bool = False


class CalPoint(BaseModel):
    """One LVDT calibration reading: block height (m) and the mean volts seen."""

    model_config = ConfigDict(frozen=True)

    volts: float
    height: float


class Tare(BaseModel):
    """Tare block statistics: mean volts, sd and sample count."""

    model_config = ConfigDict(frozen=True)

    mean: float
    sd: float
    n: int


class SetupCycle(BaseModel):
    """One clamp-slip check cycle: zero before and after, and the slip events seen."""

    model_config = ConfigDict(frozen=True)

    zero_before: float
    zero_after: float
    slip_events: int


class PlannedPoint(BaseModel):
    """One load point as the student would capture it, with how it settled and any fault."""

    model_config = ConfigDict(frozen=True)

    phase: str
    nominal_kg: float
    actual_kg: float
    u_mass_kg: float
    volts: float
    volts_sd: float
    u_volts: float
    stress_pa: float
    t_since_load_s: float
    drift_rate: float
    trace: tuple[tuple[float, float], ...] = Field(description="(t, volts) while creeping")
    fault: str | None = None


class Truth(BaseModel):
    """Ground truth a fit should recover; recorded in the provenance of the session."""

    model_config = ConfigDict(frozen=True)

    seed: int
    e_pa: float
    yield_pa: float
    cal_slope_m_per_v: float
    cal_offset_m: float
    diameter_m: float
    tare_v: float
    slip: bool
    faults: tuple[str, ...]


class Scenario(BaseModel):
    """A complete simulated lab: every input the wizard needs, in the order a student gives them."""

    model_config = ConfigDict(frozen=True)

    seed: int
    flags: ScenarioFlags
    spec: CopperSpec
    calibration: tuple[CalPoint, ...]
    tare: Tare
    diameter_m: float
    u_diameter_m: float
    hanger_kg: float
    u_hanger_kg: float
    setup: tuple[SetupCycle, ...]
    elastic: tuple[PlannedPoint, ...]
    plastic: tuple[PlannedPoint, ...]
    truth: Truth

    @property
    def provenance(self) -> DataProvenance:
        """Synthetic stamp that carries the ground truth."""
        return SYNTHETIC.with_truth(self.truth.model_dump())


class _Gen:
    """Draws the random quantities of one scenario from one seeded generator."""

    def __init__(self, seed: int, flags: ScenarioFlags) -> None:
        """Seed the generator; the same seed and flags always give the same scenario."""
        self.rng = np.random.default_rng(seed)
        self.flags = flags
        self.spec = CopperSpec()
        self.cal_slope = float(self.rng.uniform(0.004, 0.006))
        self.cal_off = float(self.rng.uniform(-0.002, 0.002))
        self.tare_v = float(self.rng.uniform(-0.2, 0.2))
        self.sd = float(self.rng.uniform(0.002, 0.006))
        self.d_meas = self.spec.diameter_m + float(self.rng.normal(0.0, 0.5e-6))

    def calibration(self) -> tuple[CalPoint, ...]:
        """5-9 gauge heights over 0-16 mm and the volts they read, in a shuffled order."""
        n = int(self.rng.integers(5, 10))
        heights = np.linspace(0.0, 0.016, n) + self.rng.normal(0.0, 1e-6, n)
        volts = (heights - self.cal_off) / self.cal_slope + self.rng.normal(0.0, 5e-4, n)
        order = self.rng.permutation(n)
        return tuple(CalPoint(volts=float(volts[i]), height=float(heights[i])) for i in order)

    def tare(self) -> Tare:
        """Hanger-only tare block."""
        n = 2000
        mean = self.tare_v + float(self.rng.normal(0.0, self.sd / np.sqrt(n)))
        return Tare(mean=mean, sd=self.sd, n=n)

    def setup(self) -> tuple[SetupCycle, ...]:
        """Clamp-check cycles: a real slip shifts the zero by ~1e-4 and logs slip events."""
        out = []
        for _ in range(CLAMP_CYCLES):
            before = float(self.rng.normal(0.0, 2e-6))
            if self.flags.slip:
                shift, ev = float(self.rng.uniform(0.8e-4, 1.4e-4)), int(self.rng.integers(1, 4))
            else:
                shift, ev = float(self.rng.normal(0.0, 3e-6)), 0
            out.append(SetupCycle(zero_before=before, zero_after=before + shift, slip_events=ev))
        return tuple(out)

    def masses(self, limit_pa: float, fine_above_pa: float | None) -> list[float]:
        """Cumulative physical hung masses (kg, 1 g steps) until stress passes `limit_pa`."""
        out: list[float] = []
        cum = 0.0
        while True:
            fine = fine_above_pa is not None and self._stress(cum) > fine_above_pa
            lo, hi = (0.004, 0.008) if fine else (0.006, 0.016)
            cum = round(cum + float(self.rng.uniform(lo, hi)), 3)
            out.append(cum)
            if self._stress(cum) >= limit_pa:
                return out

    def _stress(self, cum_kg: float) -> float:
        """Nominal stress for `cum_kg` added to the hanger."""
        return (cum_kg + HANGER_KG) * G / self.spec.area_m2


def _points(g: _Gen, phase: str, l0: float, cums: list[float]) -> list[PlannedPoint]:
    """Physically ordered load points for one run: creep traces, settle time, noisy means."""
    spec, rng = g.spec, g.rng
    scale = l0 / g.cal_slope  # volts per unit strain
    ref = spec.strain(spec.cap((HANGER_KG * G) / spec.area_m2), 0.0)
    smax = 0.0
    out: list[PlannedPoint] = []
    for cum in cums:
        u_m = float(rng.uniform(2e-4, 8e-4))
        actual = cum + float(rng.normal(0.0, u_m))
        s_true = (actual + HANGER_KG) * G / spec.area_m2
        smax = max(smax, s_true)

        def volts_at(t: float, s: float = s_true, m: float = smax) -> float:
            return g.tare_v + (spec.strain(s, m, t) - ref) * scale

        trace = []
        t_set = _HOLD_GRID_S[-1]
        for t in _HOLD_GRID_S:
            trace.append((t, volts_at(t)))
            if spec.creep_rate(s_true, t) * scale < DRIFT_SETTLED_V_PER_S:
                t_set = t
                break
        drift = spec.creep_rate(s_true, t_set) * scale
        sd_mean = g.sd / np.sqrt(_N_WINDOW)
        out.append(
            PlannedPoint(
                phase=phase,
                nominal_kg=cum,
                actual_kg=actual,
                u_mass_kg=u_m,
                volts=volts_at(t_set) + float(rng.normal(0.0, sd_mean)),
                volts_sd=g.sd,
                u_volts=2.0 * g.sd / float(np.sqrt(_N_WINDOW)),
                stress_pa=s_true,
                t_since_load_s=t_set,
                drift_rate=drift,
                trace=tuple(trace),
            )
        )
    return out


def _dup(g: _Gen, pts: list[PlannedPoint], low_pa: float) -> list[PlannedPoint]:
    """Re-post one or two low-stress masses (a student weighs the same step twice)."""
    cands = [i for i, p in enumerate(pts[:-1]) if i > 0 and p.stress_pa < low_pa]
    if not cands:
        return pts
    picks = {int(i) for i in g.rng.choice(cands, size=min(2, len(cands)), replace=False)}
    sd_mean = g.sd / np.sqrt(_N_WINDOW)
    out: list[PlannedPoint] = []
    for i, p in enumerate(pts):
        out.append(p)
        if i in picks:
            out.append(p.model_copy(update={"volts": p.volts + float(g.rng.normal(0.0, sd_mean))}))
    return out


def _swap(g: _Gen, pts: list[PlannedPoint], low_pa: float) -> list[PlannedPoint]:
    """Post one pair of adjacent low-stress steps in the wrong order."""
    cands = [
        i
        for i in range(1, len(pts) - 1)
        if pts[i].stress_pa < low_pa and pts[i + 1].stress_pa < low_pa
    ]
    if cands:
        i = int(g.rng.choice(cands))
        pts[i], pts[i + 1] = pts[i + 1], pts[i]
    return pts


def _fault(g: _Gen, pts: list[PlannedPoint], kind: str) -> list[PlannedPoint]:
    """Insert a spiked or saturated extra capture just before a mid-run step."""
    i = len(pts) // 2
    base = pts[i]
    volts = base.volts + 0.5 if kind == "spike" else _FULL_SCALE_V
    bad = base.model_copy(update={"volts": volts, "fault": kind})
    return [*pts[:i], bad, *pts[i:]]


def generate_scenario(seed: int, flags: ScenarioFlags | None = None) -> Scenario:
    """Build the whole simulated lab for `seed`; deterministic, and the truth is recorded."""
    flags = flags or ScenarioFlags()
    g = _Gen(seed, flags)
    spec = g.spec
    sy = spec.offset_yield_pa()
    low = 0.8 * spec.onset_pa
    elastic = _points(g, "elastic", LONG_L0_M, g.masses(0.6 * spec.onset_pa, None))
    plastic = _points(g, "plastic", SHORT_L0_M, g.masses(1.1 * sy, 0.9 * spec.onset_pa))
    if flags.out_of_order:
        elastic, plastic = _swap(g, elastic, low), _swap(g, plastic, low)
    if flags.duplicates:
        elastic, plastic = _dup(g, elastic, low), _dup(g, plastic, low)
    faults = [k for k, on in (("spike", flags.spike), ("saturation", flags.saturation)) if on]
    if flags.dropped_frames:
        faults.append("dropped_frames")
    for k in faults:
        if k != "dropped_frames":
            elastic = _fault(g, elastic, k)
    truth = Truth(
        seed=seed,
        e_pa=spec.e_pa,
        yield_pa=sy,
        cal_slope_m_per_v=g.cal_slope,
        cal_offset_m=g.cal_off,
        diameter_m=spec.diameter_m,
        tare_v=g.tare_v,
        slip=flags.slip,
        faults=tuple(faults),
    )
    _log.info(
        "scenario seed=%d: %d elastic, %d plastic points, faults=%s, slip=%s",
        seed,
        len(elastic),
        len(plastic),
        faults,
        flags.slip,
    )
    return Scenario(
        seed=seed,
        flags=flags,
        spec=spec,
        calibration=g.calibration(),
        tare=g.tare(),
        diameter_m=g.d_meas,
        u_diameter_m=1e-6,
        hanger_kg=HANGER_KG,
        u_hanger_kg=1e-4,
        setup=g.setup(),
        elastic=tuple(elastic),
        plastic=tuple(plastic),
        truth=truth,
    )
