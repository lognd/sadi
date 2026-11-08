# Incremental replay

Status: current

Owners: ~2RWJ137, ~AZ8KDXT. Code: `python/sadi/store/incremental.py`.

`sadi.store.incremental.IncrementalReplay` serves the server's per-action
state (`SessionService._replay`) without re-walking the whole WAL.

Why: `recover_state` CRC-verifies every frame of every segment. The
simulator writes ~200k raw records per minute, so two full walks per action
made `POST /api/session/points` take 3s, 30s and more, starved the writer
and surfaced as a false "data disk is not responding" (the writer waited
on durability while replay held the GIL).

How: the first call (and every fallback) does a full `recover_state`-style
replay and remembers the fold plus the byte position after the last applied
frame. Later calls read only bytes appended past that position, verify each
frame (CRC32C, header, seq continuity) and apply it to the cached fold.

Safety rule (data safety is the mandate): the fast path never guesses. A CRC
failure, seq gap, bad header, SEAL record, missing or changed segment, or a
torn tail all discard the cache and run the full verified replay, which stays
the single authority for corruption handling. The cached result is therefore
always equal to `recover_state` over the same bytes. Nothing is written,
truncated or reordered; the WAL is only read.

Tests: `python/tests/store/test_incremental.py` (hypothesis equivalence of
incremental vs full replay on random event sequences, restart, torn tail,
undo/redo) and `python/tests/server/test_action_latency.py` (200k raw
records, then 20 actions under a bound).

## Curve source and notes (~AZ8KDXT)

`SessionService.notes()` and the active-session curve source
(`curve_source.make_curve_source`, via `session_events(sdir, replayer)`) use
the same machinery under the same safety contract. `IncrementalReplay.notes()`
returns every JSON NOTE payload in WAL order; the tail loop collects notes as it
applies frames, and a rebase re-collects them (notes are not in snapshots, so a
snapshot base triggers one full WAL walk for notes). The curve source keeps one
`IncrementalReplay` per session dir behind a lock and drops caches of sessions
that are no longer the newest. Any anomaly falls back to the full verified
replay; results equal the previous full scans. `session_events(sdir)` without a
replayer still does a full `recover_state`.

Tests: `python/tests/store/test_incremental_notes.py` (equivalence, restart,
torn tail) and `python/tests/server/test_curve_notes_latency.py` (200k raw
records, repeated notes and curve calls under a bound).
