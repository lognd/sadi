"""Read-only CurveSource over the open session (path supplied by the SessionService)."""

# frob:ticket 01M726PZNXA6BEXH97TQPK3176
# frob:ticket 01M6WMXEM0M76VKMN2WF3C3VYD
# frob:ticket 01M6X465ZVYG4B9Y79QAZ8KDXT
# frob:ticket 01M6X8XTQ31XRDC5BZFNQZXN6Q
# frob:ticket 01M6X9CP3SGVZ93H22ARANVN2E

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from typani import Err, Ok, Result, propagate

from sadi.core.point_inputs import (
    CalibrationInputs,
    ClampInputs,
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
    """Return the newest session dir by name, or None; CLI/offline use only, never the request path.

    Names sort by family creation stamp, so this is NOT the open session once families resume.
    """
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
    if isinstance(p, ClampInputs):  # clamp cycles are not curve events
        return None  # frob:ticket 01M6XA21KQE5WEXAN39683H4S9
    # frob:ticket 01M6WP144S0ENPQESCQEQ6NT5Y
    meta = parse_meta(cp.point)
    return LoadPoint(
        settled=meta.settled,
        forced_early=meta.forced_early,
        drift_rate=meta.drift_rate,
        t_since_load_s=meta.t_since_load_s,
        point_id=cp.point.point_id,
        phase=cp.point.phase,  # frob:ticket 01M729642YCP4MRYBWBNQBYW7A
        volts=p.volts,
        u_volts=p.u_volts,
        volts_sd=p.volts_sd,  # frob:ticket 01M6WX3GGD2VSGEY1GT2X49DSV
        mass_kg=p.mass_kg,
        u_mass_kg=p.u_mass_kg,
    )


# frob:ticket 01M6WP144S0ENPQESCQEQ6NT5Y
@propagate
def session_events(
    sdir: Path, replayer: IncrementalReplay | None = None
) -> Result[list[LiveEvent], str]:
    """Replay a session dir into LiveEvents; load points carry settled/forced-early/drift flags.

    Excluded load points are kept and flagged (ExcludePoint); excluded cal/tare/specimen are
    omitted.

    With `replayer` (tracking `sdir`) the fold is incremental yet equal to a full replay.
    """
    state: Result[ReplayState, object] = (
        recover_state(sdir) if replayer is None else replayer.state()
    )
    events: list[LiveEvent] = []
    for cp in state.map_err(str).unwrap().view().points:
        ev = _event(cp)
        if ev is None:
            _log.warning("curve source: point %s has unusable inputs", cp.point.point_id)
            continue
        if isinstance(ev, LoadPoint) and ev.forced_early:
            _log.warning("curve source: point %s was forced early", cp.point.point_id)
        if cp.excluded and not isinstance(ev, LoadPoint):
            # frob:ticket 01M7230XQFMBWVCNP4NASD05SE
            # Cal/tare/specimen carry no id in the fold: leave them out of the events (the WAL
            # keeps them) so export and plots agree with the results.
            _log.info("curve source: excluded %s point %s left out", ev.kind, cp.point.point_id)
            continue
        events.append(ev)
        if cp.excluded and isinstance(ev, LoadPoint):
            events.append(ExcludePoint(point_id=ev.point_id))
    return Ok(events)


_PLASTIC_PHASE = "plastic"  # rows of the short-specimen run; never part of the E fit curve


def load_curve(
    data_root: Path, cache: dict[Path, IncrementalReplay] | None = None
) -> Result[Sequence[CurvePoint], RefitError]:
    """Build the curve of the newest session dir under `data_root` (CLI/offline use only)."""
    sdir = active_session(data_root)
    if sdir is None:
        _log.info("curve source: no session under %s", data_root)
        return Err(RefitError.NoData)
    return load_session_curve(sdir, cache)


def load_session_curve(
    sdir: Path, cache: dict[Path, IncrementalReplay] | None = None
) -> Result[Sequence[CurvePoint], RefitError]:
    """Build the active (non-excluded, elastic or unphased) stress-strain curve from `sdir`'s events.

    `cache` (session dir -> IncrementalReplay) makes repeat calls read only newly appended frames.
    """
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
        if row.phase == _PLASTIC_PHASE:
            # frob:ticket 01M72D3CTDED2MGDY721RSM8M4
            # The plastic run is a different specimen (own L0): E is fitted on elastic rows only.
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
REVERIFY_INTERVAL_S = 30.0  # live views re-verify all applied WAL bytes at least this often


class SessionReplayCache:
    """One IncrementalReplay per session dir, shared by curve, plots and export (thread-safe).

    Incremental tailing never re-reads bytes it already applied, so corruption there would go
    unnoticed. Hence a cached entry older than `reverify_interval_s` is dropped and rebuilt by a
    full CRC-verified replay, and `events(..., verify=True)` (used by export) always does so.
    """

    def __init__(
        self,
        reverify_interval_s: float = REVERIFY_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Start empty; replayers are created on first use of a session dir."""
        self._cache: dict[Path, IncrementalReplay] = {}
        self._verified_at: dict[Path, float] = {}
        self._interval = reverify_interval_s
        self._clock = clock
        self._lock = threading.Lock()

    def _evict(self) -> None:
        """Drop the oldest-inserted entries beyond the bound (caller holds the lock)."""
        while len(self._cache) > _MAX_CACHED:
            old = next(iter(self._cache))
            self._cache.pop(old)
            self._verified_at.pop(old, None)

    def _replayer(self, sdir: Path, verify: bool) -> IncrementalReplay:
        """Return the replayer for `sdir`, fresh (so fully verified) if forced or stale."""
        now = self._clock()
        have = self._cache.get(sdir)
        stale = have is not None and now - self._verified_at.get(sdir, 0.0) >= self._interval
        if have is None or verify or stale:
            if have is not None:
                _log.info("replay cache: full re-verify of %s (forced=%s)", sdir.name, verify)
            have = IncrementalReplay(sdir)  # first state() is a full CRC-verified replay
            self._cache[sdir] = have
            self._verified_at[sdir] = now
        return have

    # frob:ticket 01M6X9CP3SGVZ93H22ARANVN2E
    def events(self, sdir: Path, *, verify: bool = False) -> Result[list[LiveEvent], str]:
        """Return `session_events(sdir)` via the cache; `verify=True` forces a full verified replay.

        Any error drops the cached entry so corrupt state is never served again.
        """
        with self._lock:
            replayer = self._replayer(sdir, verify)
            self._evict()
            res = session_events(sdir, replayer)
            if res.is_err:
                _log.error("replay cache: dropping %s after error: %s", sdir.name, res.danger_err)
                self._cache.pop(sdir, None)
                self._verified_at.pop(sdir, None)
            return res

    def curve(self, sdir: Path) -> Result[Sequence[CurvePoint], RefitError]:
        """Return the curve of session `sdir`, reading only newly appended WAL frames."""
        with self._lock:
            self._replayer(sdir, False)  # applies the periodic re-verify policy
            res = load_session_curve(sdir, self._cache)
            self._evict()
            return res


def make_curve_source(
    open_session: Callable[[], Path | None], cache: SessionReplayCache | None = None
) -> CurveSource:
    """Return a CurveSource over the open session (incremental WAL tail).

    `open_session` yields the open session dir, or None; None gives RefitError.NoOpenSession.
    """
    shared = cache if cache is not None else SessionReplayCache()

    def source() -> Result[Sequence[CurvePoint], RefitError]:
        """Delegate to the shared, lock-guarded cache for the currently open session."""
        sdir = open_session()
        if sdir is None:
            _log.info("curve source: no session is open")
            return Err(RefitError.NoOpenSession)
        return shared.curve(sdir)

    return source
