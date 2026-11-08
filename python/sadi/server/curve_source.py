"""Read-only CurveSource over the active session: newest session dir under the data root."""

# frob:ticket 01M6WMXEM0M76VKMN2WF3C3VYD
# frob:ticket 01M6X465ZVYG4B9Y79QAZ8KDXT
# frob:ticket ~NQZXN6Q

from __future__ import annotations

import threading
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from typani import Err, Ok, Result

from sadi.core.point_inputs import (
    CalibrationInputs,
    SpecimenInputs,
    TareInputs,
    parse_inputs,
    parse_meta,
)
from sadi.labs.lctt.export_csv import build_document
from sadi.labs.lctt.live import (
    CalPoint,
    ExcludePoint,
    LiveEvent,
    LoadPoint,
    SpecimenSetup,
    TareBlock,
)
from sadi.labs.lctt.modulus import CurvePoint
from sadi.logging_setup import get_logger
from sadi.server.routes_stress_strain import CurveSource, RefitError
from sadi.store.events import CurrentPoint, ReplayState, recover_state
from sadi.store.incremental import IncrementalReplay
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


def _event(cp: CurrentPoint) -> LiveEvent | None:
    """Map one replayed point to a LiveEvent via the shared phase mapping; None if unusable."""
    parsed = parse_inputs(cp.point.phase, cp.inputs)
    if parsed.is_err:
        return None
    p = parsed.danger_ok
    if isinstance(p, CalibrationInputs):
        return CalPoint(volts=p.volts, height=p.height)
    if isinstance(p, TareInputs):
        return TareBlock(mean=p.mean, sd=p.sd, n=p.n)
    if isinstance(p, SpecimenInputs):
        return SpecimenSetup(
            diameter=p.diameter,
            u_diameter=p.u_diameter,
            hanger_kg=p.hanger_kg,
            u_hanger_kg=p.u_hanger_kg,
        )
    # frob:ticket 01M6WP144S0ENPQESCQEQ6NT5Y
    meta = parse_meta(cp.point)
    return LoadPoint(
        settled=meta.settled,
        forced_early=meta.forced_early,
        drift_rate=meta.drift_rate,
        t_since_load_s=meta.t_since_load_s,
        point_id=cp.point.point_id,
        volts=p.volts,
        u_volts=p.u_volts,
        volts_sd=p.volts_sd,  # frob:ticket 01M6WX3GGD2VSGEY1GT2X49DSV
        mass_kg=p.mass_kg,
        u_mass_kg=p.u_mass_kg,
    )


# frob:ticket 01M6WP144S0ENPQESCQEQ6NT5Y
def session_events(
    sdir: Path, replayer: IncrementalReplay | None = None
) -> Result[list[LiveEvent], str]:
    """Replay a session dir into LiveEvents; load points carry settled/forced-early/drift flags.

    With `replayer` (tracking `sdir`) the fold is incremental yet equal to a full replay.
    """
    state: Result[ReplayState, object] = (
        recover_state(sdir) if replayer is None else replayer.state()
    )
    if state.is_err:
        return Err(str(state.danger_err))
    events: list[LiveEvent] = []
    for cp in state.danger_ok.view().points:
        ev = _event(cp)
        if ev is None:
            _log.warning("curve source: point %s has unusable inputs", cp.point.point_id)
            continue
        if isinstance(ev, LoadPoint) and ev.forced_early:
            _log.warning("curve source: point %s was forced early", cp.point.point_id)
        events.append(ev)
        if cp.excluded and isinstance(ev, LoadPoint):
            events.append(ExcludePoint(point_id=ev.point_id))
    return Ok(events)


def load_curve(
    data_root: Path, cache: dict[Path, IncrementalReplay] | None = None
) -> Result[Sequence[CurvePoint], RefitError]:
    """Build the active (non-excluded) stress-strain curve from the active session's events.

    `cache` (session dir -> IncrementalReplay) makes repeat calls read only newly appended frames.
    """
    sdir = active_session(data_root)
    if sdir is None:
        _log.info("curve source: no session under %s", data_root)
        return Err(RefitError.NoData)
    replayer = None
    if cache is not None:
        replayer = cache.setdefault(sdir, IncrementalReplay(sdir))
    res = session_events(sdir, replayer)
    if res.is_err:
        _log.error("curve source: replay of %s failed: %s", sdir.name, res.danger_err)
        return Err(RefitError.NoData)
    events = res.danger_ok
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


_MAX_CACHED = 4  # sessions kept warm; evicting one only costs a verified full replay later


class SessionReplayCache:
    """One IncrementalReplay per session dir, shared by curve, plots and export (thread-safe)."""

    def __init__(self) -> None:
        """Start empty; replayers are created on first use of a session dir."""
        self._cache: dict[Path, IncrementalReplay] = {}
        self._lock = threading.Lock()

    def _evict(self) -> None:
        """Drop the oldest-inserted entries beyond the bound (caller holds the lock)."""
        while len(self._cache) > _MAX_CACHED:
            self._cache.pop(next(iter(self._cache)))

    def events(self, sdir: Path) -> Result[list[LiveEvent], str]:
        """Return `session_events(sdir)` via the cached replayer (full-replay fallback inside)."""
        with self._lock:
            replayer = self._cache.setdefault(sdir, IncrementalReplay(sdir))
            self._evict()
            return session_events(sdir, replayer)

    def curve(self, data_root: Path) -> Result[Sequence[CurvePoint], RefitError]:
        """Return the active-session curve, reading only newly appended WAL frames."""
        with self._lock:
            res = load_curve(data_root, self._cache)
            self._evict()
            return res


def make_curve_source(data_root: Path, cache: SessionReplayCache | None = None) -> CurveSource:
    """Return a CurveSource over the active session under `data_root` (incremental WAL tail)."""
    shared = cache if cache is not None else SessionReplayCache()

    def source() -> Result[Sequence[CurvePoint], RefitError]:
        """Delegate to the shared, lock-guarded cache."""
        return shared.curve(data_root)

    return source
