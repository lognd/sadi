"""The one definition of the WAL POINT phase -> inputs mapping, shared by writer and reader.

The recording path builds POINT events with `build_point`; the server's curve source reads them
back with `parse_inputs`. Phases: calibration (volts, height), tare (mean, sd, n), specimen
(diameter, u_diameter, hanger_kg, u_hanger_kg) and any other phase name is a load point (volts,
mass_kg, optional u_volts, u_mass_kg). Description: docs/server/app.md.
"""

# frob:ticket 01M6WN40B3NY98XEFCEHNRCGB7
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.core.events import PointV1, PointWindow
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

PHASE_CALIBRATION = "calibration"
PHASE_TARE = "tare"
PHASE_SPECIMEN = "specimen"
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


class PointMeta(BaseModel):
    """Settle provenance of a point: time since load, drift rate and the settled/forced flags."""

    model_config = ConfigDict(frozen=True)
    t_since_load_s: float | None = None
    drift_rate: float | None = None
    settled: bool = False
    forced_early: bool = False


PointInputs = CalibrationInputs | TareInputs | SpecimenInputs | LoadInputs


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
