"""The one definition of the WAL POINT phase -> inputs mapping, shared by writer and reader.

The recording path builds POINT events with `build_point`; the server's curve source reads them
back with `parse_inputs`. Phases: calibration (volts, height), tare (mean, sd, n), specimen
(diameter, u_diameter, hanger_kg, u_hanger_kg), setup (zero_before, zero_after, slip_events)
and any other phase name is a load point (volts, mass_kg, optional u_volts, u_mass_kg).
Description: docs/server/app.md.
"""

# frob:ticket 01M6WN40B3NY98XEFCEHNRCGB7
# frob:ticket 01M6XA21KQE5WEXAN39683H4S9
from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.core.events import PointV1, PointWindow
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

PHASE_CALIBRATION = "calibration"
PHASE_TARE = "tare"
PHASE_SPECIMEN = "specimen"
#: Wizard Setup step phase: one clamp-check cycle record (zeros and observed slips).
PHASE_SETUP = "setup"
#: Default phase name for a load point; any phase outside the three above reads as a load point.
PHASE_LOAD = "load"


class _Inputs(BaseModel):
    """Base for typed POINT inputs: frozen, and the phase they are recorded under."""

    model_config = ConfigDict(frozen=True)
    phase: str = PHASE_LOAD


class CalibrationInputs(_Inputs):
    """One calibration sample: LVDT volts at a known height (m)."""

    phase: str = PHASE_CALIBRATION
    volts: float
    height: float


class TareInputs(_Inputs):
    """One tare block: mean volts, sample sd and sample count."""

    phase: str = PHASE_TARE
    mean: float
    sd: float = 0.0
    n: int


class SpecimenInputs(_Inputs):
    """Specimen diameter and hanger mass in SI with standard uncertainties."""

    phase: str = PHASE_SPECIMEN
    diameter: float
    u_diameter: float = 0.0
    hanger_kg: float = 0.0
    u_hanger_kg: float = 0.0


class LoadInputs(_Inputs):
    """A load point: block-mean volts and total hanging mass (kg) with uncertainties."""

    volts: float
    mass_kg: float
    u_volts: float = 0.0
    u_mass_kg: float = 0.0
    # frob:ticket 01M6WX3GGD2VSGEY1GT2X49DSV
    volts_sd: float | None = None  # per-sample std dev of the raw volts in the window


class ClampInputs(_Inputs):
    """One clamp-check cycle: strain zero before loading and after unloading, slips observed."""

    phase: str = PHASE_SETUP
    zero_before: float
    zero_after: float
    slip_events: int = 0


class PointMeta(BaseModel):
    """Settle provenance of a point: time since load, drift rate and the settled/forced flags."""

    model_config = ConfigDict(frozen=True)
    t_since_load_s: float | None = None
    drift_rate: float | None = None
    settled: bool = False
    forced_early: bool = False


PointInputs = CalibrationInputs | TareInputs | SpecimenInputs | LoadInputs | ClampInputs


def _num(inputs: dict[str, Any], key: str) -> float | None:
    """Return inputs[key] as a float, None when absent or not numeric."""
    val = inputs.get(key)
    return float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else None


def _opt(inputs: dict[str, Any], key: str) -> float:
    """Return an optional numeric input, 0.0 when absent or not numeric."""
    return _num(inputs, key) or 0.0


def parse_inputs(phase: str, inputs: dict[str, Any]) -> Result[PointInputs, str]:
    """Read a POINT's `inputs` by its phase; Err names the missing required key."""
    if phase == PHASE_CALIBRATION:
        v, h = _num(inputs, "volts"), _num(inputs, "height")
        if v is None or h is None:
            return Err("calibration needs volts and height")
        return Ok(CalibrationInputs(volts=v, height=h))
    if phase == PHASE_TARE:
        m, n = _num(inputs, "mean"), _num(inputs, "n")
        if m is None or n is None:
            return Err("tare needs mean and n")
        return Ok(TareInputs(mean=m, sd=_opt(inputs, "sd"), n=int(n)))
    if phase == PHASE_SPECIMEN:
        d = _num(inputs, "diameter")
        if d is None:
            return Err("specimen needs diameter")
        return Ok(
            SpecimenInputs(
                diameter=d,
                u_diameter=_opt(inputs, "u_diameter"),
                hanger_kg=_opt(inputs, "hanger_kg"),
                u_hanger_kg=_opt(inputs, "u_hanger_kg"),
            )
        )
    if phase == PHASE_SETUP:
        zb, za = _num(inputs, "zero_before"), _num(inputs, "zero_after")
        if zb is None or za is None or not (math.isfinite(zb) and math.isfinite(za)):
            return Err("clamp check needs finite zero_before and zero_after")
        slips = _num(inputs, "slip_events")
        return Ok(ClampInputs(zero_before=zb, zero_after=za, slip_events=max(0, int(slips or 0))))
    v, mass = _num(inputs, "volts"), _num(inputs, "mass_kg")
    if v is None or mass is None:
        return Err("load point needs volts and mass_kg")
    return Ok(
        LoadInputs(
            phase=phase,
            volts=v,
            mass_kg=mass,
            u_volts=_opt(inputs, "u_volts"),
            u_mass_kg=_opt(inputs, "u_mass_kg"),
            volts_sd=_num(inputs, "volts_sd"),  # frob:ticket 01M6WX3GGD2VSGEY1GT2X49DSV
        )
    )


#: Plausibility limits for captured inputs (SI units); see `check_ranges`.
MIN_DIAMETER_M = 0.05e-3
MAX_DIAMETER_M = 5e-3
#: LVDT stroke is a few centimetres; a metre-scale height is a unit slip (mm typed as m).
MAX_HEIGHT_M = 0.1
#: Heights are measured relative to a zero reference, so small noise below zero is legitimate.
MIN_HEIGHT_M = -1e-3
#: Hanging masses are a few kg at most; larger values are probably grams typed as kg.
MAX_MASS_KG = 20.0
MAX_VOLTS = 100.0
MAX_STRAIN_ZERO = 1.0
MAX_TARE_N = 100_000_000
#: SI unit -> the thousandth unit people mistakenly type instead.
_MISTAKEN_UNIT = {"metres": "millimetres", "kilograms": "grams"}


def _finite(items: dict[str, float]) -> str | None:
    """Return a message naming the first non-finite value in `items`, else None."""
    for name, val in items.items():
        if not math.isfinite(val):
            return f"{name} must be a finite number (got {val}); NaN and Infinity are not stored"
    return None


def _bounded(name: str, val: float, lo: float, hi: float, unit: str) -> str | None:
    """Return a unit-aware message when `val` is outside [lo, hi], else None."""
    if lo <= val <= hi:
        return None
    other = _MISTAKEN_UNIT.get(unit)
    if other is not None and val > hi and lo <= val / 1e3 <= hi:
        return f"{name} is in {unit}; {val:g} looks like {other}, did you mean {val / 1e3:g}?"
    return f"{name} is in {unit}; {val:g} is outside the plausible range {lo:g}..{hi:g} {unit}"


def _nonneg(items: dict[str, float], unit: str) -> str | None:
    """Return a message for the first negative value in `items`, else None."""
    for name, val in items.items():
        if val < 0:
            return f"{name} is in {unit} and cannot be negative (got {val:g})"
    return None


def check_ranges(inputs: PointInputs) -> Result[PointInputs, str]:
    """Reject non-finite or implausible inputs with a unit-aware message; Ok returns `inputs`.

    This guards the capture write path only; reading old logs stays lenient (`parse_inputs`).
    """
    fields = {k: float(v) for k, v in inputs.model_dump(exclude={"phase"}).items() if v is not None}
    problem = _finite(fields) or _check_phase(inputs)
    if problem is not None:
        _log.warning("input rejected (%s): %s", inputs.phase, problem)
        return Err(problem)
    return Ok(inputs)


def _check_phase(inputs: PointInputs) -> str | None:
    """Phase-specific plausibility checks on already finite inputs."""
    v = MAX_VOLTS
    if isinstance(inputs, CalibrationInputs):
        return _bounded("volts", inputs.volts, -v, v, "volts") or _bounded(
            "height", inputs.height, MIN_HEIGHT_M, MAX_HEIGHT_M, "metres"
        )
    if isinstance(inputs, TareInputs):
        if not 1 <= inputs.n <= MAX_TARE_N:
            return f"n is a sample count and must be between 1 and {MAX_TARE_N} (got {inputs.n})"
        return _bounded("mean", inputs.mean, -v, v, "volts") or _nonneg({"sd": inputs.sd}, "volts")
    if isinstance(inputs, SpecimenInputs):
        return (
            _bounded("diameter", inputs.diameter, MIN_DIAMETER_M, MAX_DIAMETER_M, "metres")
            or _nonneg({"u_diameter": inputs.u_diameter}, "metres")
            or _bounded("hanger_kg", inputs.hanger_kg, 0.0, MAX_MASS_KG, "kilograms")
            or _nonneg({"u_hanger_kg": inputs.u_hanger_kg}, "kilograms")
        )
    if isinstance(inputs, LoadInputs):
        return (
            _bounded("volts", inputs.volts, -v, v, "volts")
            or _bounded("mass_kg", inputs.mass_kg, 0.0, MAX_MASS_KG, "kilograms")
            or _nonneg({"u_volts": inputs.u_volts, "u_mass_kg": inputs.u_mass_kg}, "SI units")
        )
    z = MAX_STRAIN_ZERO
    return _bounded("zero_before", inputs.zero_before, -z, z, "strain") or _bounded(
        "zero_after", inputs.zero_after, -z, z, "strain"
    )


def check_window(window: PointWindow, durable_seq: int | None = None) -> Result[PointWindow, str]:
    """Reject a sample window that is negative, reversed or beyond the durable raw seq.

    The upper bound applies only when `durable_seq` is given; the server passes None because it has
    no raw index, so synthetic/replayed windows stay accepted and only sign/ordering is enforced.

    The seqs are WAL seqs of RAW_BLOCK records: a point cannot average data that is not (yet)
    durable. Server-side volts are not re-derived from the window (documented limitation).
    """
    w = window
    problem = None
    if min(w.first_raw_seq, w.last_raw_seq, w.first_sample, w.last_sample) < 0:
        problem = "window seqs and sample offsets are counts and cannot be negative"
    elif w.first_raw_seq > w.last_raw_seq or (
        w.first_raw_seq == w.last_raw_seq and w.first_sample > w.last_sample
    ):
        problem = "window is reversed: first must not come after last"
    elif durable_seq is not None and w.last_raw_seq > durable_seq:
        problem = (
            f"window ends at raw seq {w.last_raw_seq} but only seq {durable_seq} is durable; "
            "a point can only average data already recorded"
        )
    if problem is not None:
        _log.warning("window rejected: %s (durable_seq=%s)", problem, durable_seq)
        return Err(problem)
    return Ok(window)


def build_point(inputs: PointInputs, window: PointWindow, meta: PointMeta | None = None) -> PointV1:
    """Build the POINT payload for typed inputs (and optional settle meta); keys match parsing."""
    raw = inputs.model_dump(exclude={"phase"})
    m = meta if meta is not None else PointMeta()
    _log.info(
        "point built: phase=%s keys=%s settled=%s forced_early=%s",
        inputs.phase,
        sorted(raw),
        m.settled,
        m.forced_early,
    )
    return PointV1(phase=inputs.phase, window=window, inputs=raw, **m.model_dump())


def parse_meta(point: PointV1) -> PointMeta:
    """Read a POINT's settle meta; events written before the fields existed read as defaults."""
    return PointMeta(
        t_since_load_s=point.t_since_load_s,
        drift_rate=point.drift_rate,
        settled=point.settled,
        forced_early=point.forced_early,
    )
