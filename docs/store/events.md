# Event log and snapshots

Status: current

Owner: ~K6BT3MG. Code: `python/sadi/store/events.py`, `python/sadi/store/snapshot.py`.
Tests: `python/tests/store/test_events.py`.
Design: [data-safety.md](../data-safety.md) sections 2.3, 3.3, 9.1, 9.2 and 15.

## Event log

Points, window edits, exclusions, settings changes and markers are all WAL records
(see [wal.md](wal.md)). Nothing is stored as mutable state. Current state is the fold of
the log: `replay(records, base)` returns a frozen `ReplayState` holding the full history
(points, every edit, settings log, markers, skipped records). `ReplayState.view()` derives
the current values on demand.

- Edits are appended, never applied in place. Undo and redo are edits whose `supersedes`
  names an `edit_id`; include/exclude are ordinary edits. History is never removed.
- Unknown or undecodable records go to `skipped`; semantically odd ones (unknown target,
  undo of an unknown edit) go to `View.anomalies`. Replay continues past both.
- Replay is pure and deterministic: same records give an identical state and JSON.
- `replay_wal(wal_dir)` reads through the read-only `WalReader`; it never truncates or
  rewrites. Mid-log corruption is `Err(EventsWal)` with the files untouched.

## Snapshots

A snapshot caches `ReplayState` so recovery does not replay the whole log. It is only an
optimisation; the WAL is the truth.

Write path (`write_snapshot`): exclusive dot-prefixed tmp file in `snapshots/`, write,
fsync, no-replace publish (hard link then unlink tmp, with an exists-check fallback),
fsync of the directory, then an optional best-effort `SNAPSHOT_REF` record. An existing
snapshot is never overwritten; name collisions get a suffix. A `covers_seq` beyond the
verified WAL is refused (`SnapshotAhead`). Failure at any step leaves no partial final
file.

The file is one WAL frame (type 0x0A, seq = `covers_seq`) with a JSON `SnapshotV1`
payload that carries the SHA-256 prefix hash over `seq || crc` of every data record up to
`covers_seq`.

## Recovery

`recover_state(session_dir)` picks snapshots by descending `covers_seq` and accepts the
first whose frame CRC is valid, whose `covers_seq` does not exceed the verified last seq,
and whose prefix hash matches the WAL. Corrupt, stale, ahead-of-log or unparsable
snapshots and leftover `.tmp` files are logged and ignored, never deleted. It then replays
only the WAL tail after the snapshot, or the whole log if no snapshot qualifies.

See also [Derived exports with provenance](exports.md) for the export side of the same atomic-publish rules.
