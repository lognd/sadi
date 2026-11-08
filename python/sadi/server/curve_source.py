"""Read-only CurveSource over the active session: newest session dir under the data root."""

# frob:ticket 01M6WMXEM0M76VKMN2WF3C3VYD

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from typani import Err, Ok, Result

from sadi.labs.lctt.export_csv import build_document
from sadi.labs.lctt.live import CalPoint, ExcludePoint, LiveEvent, LoadPoint, SpecimenSetup, TareBlock
from sadi.labs.lctt.modulus import CurvePoint
from sadi.logging_setup import get_logger
from sadi.server.routes_stress_strain import CurveSource, RefitError
from sadi.store.events import CurrentPoint, recover_state
from sadi.store.session import SESSIONS_DIRNAME
from sadi.uncertainty import Measured

_log = get_logger(__name__)

# Document date is metadata only; a constant keeps the derivation pure and deterministic.
_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def active_session(data_root: Path) -> Path | None:
    """Return the newest session dir (names sort by UTC stamp), or None; never writes."""
    base = data_root / SESSIONS_DIRNAME
    try:
        dirs = sorted(p for p in base.iterdir() if p.is_dir() and (p / "wal").is_dir())
    except OSError:
        return None
    return dirs[-1] if dirs else None


def _num(inputs: dict[str, object], key: str, default: float | None = None) -> float | None:
    """Return inputs[key] as a float, `default` when absent or not numeric."""
    val = inputs.get(key, default)
    return float(val) if isinstance(val, (int, float)) and not isinstance(val, bool) else default


def _event(cp: CurrentPoint) -> LiveEvent | None:
    """Map one replayed point to a LiveEvent by its phase; None when inputs are unusable."""
    i, phase = cp.inputs, cp.point.phase
    if phase == "calibration":
        v, h = _num(i, "volts"), _num(i, "height")
        return CalPoint(volts=v, height=h) if v is not None and h is not None else None
    if phase == "tare":
        m, sd, n = _num(i, "mean"), _num(i, "sd", 0.0), _num(i, "n")
        if m is None or sd is None or n is None:
            return None
        return TareBlock(mean=m, sd=sd, n=int(n))
    if phase == "specimen":
        d = _num(i, "diameter")
        if d is None:
            return None
        return SpecimenSetup(
            diameter=d,
            u_diameter=_num(i, "u_diameter", 0.0) or 0.0,
            hanger_kg=_num(i, "hanger_kg", 0.0) or 0.0,
            u_hanger_kg=_num(i, "u_hanger_kg", 0.0) or 0.0,
        )
    v, mass = _num(i, "volts"), _num(i, "mass_kg")
    if v is None or mass is None:
        return None
    return LoadPoint(
        point_id=cp.point.point_id,
        volts=v,
        u_volts=_num(i, "u_volts", 0.0) or 0.0,
        mass_kg=mass,
        u_mass_kg=_num(i, "u_mass_kg", 0.0) or 0.0,
    )


def load_curve(data_root: Path) -> Result[Sequence[CurvePoint], RefitError]:
    """Build the active (non-excluded) stress-strain curve from the active session's events."""
    sdir = active_session(data_root)
    if sdir is None:
        _log.info("curve source: no session under %s", data_root)
        return Err(RefitError.NoData)
    state = recover_state(sdir)
    if state.is_err:
        _log.error("curve source: replay of %s failed: %s", sdir.name, state.danger_err)
        return Err(RefitError.NoData)
    events: list[LiveEvent] = []
    for cp in state.danger_ok.view().points:
        ev = _event(cp)
        if ev is None:
            _log.warning("curve source: point %s has unusable inputs", cp.point.point_id)
            continue
        events.append(ev)
        if cp.excluded and isinstance(ev, LoadPoint):
            events.append(ExcludePoint(point_id=ev.point_id))
    doc = build_document(events, date=_EPOCH)
    if doc.is_err:
        _log.info("curve source: %s not ready: %s", sdir.name, doc.danger_err.name)
        return Err(RefitError.NoData)
    out: list[CurvePoint] = []
    for row in doc.danger_ok.rows:
        if row.excluded:
            continue
        stress = Measured.create(row.stress_pa, row.u_stress_pa, "Pa")
        strain = Measured.create(row.strain, row.u_strain, "")
        if stress.is_err or strain.is_err:
            _log.error("curve source: bad measured values at point %s", row.point_id)
            return Err(RefitError.NoData)
        out.append(CurvePoint(index=len(out), stress=stress.danger_ok, strain=strain.danger_ok))
    _log.info("curve source: %d points from %s", len(out), sdir.name)
    return Ok(out)


def make_curve_source(data_root: Path) -> CurveSource:
    """Return a CurveSource that re-reads the active session under `data_root` on every call."""
    return lambda: load_curve(data_root)
