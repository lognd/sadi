# Emergency spill import

Status: current

Owner: ~JQPFW6F. Code: `python/sadi/store/spill.py`. Tests: `python/tests/store/test_spill.py`.
Design: [data-safety.md](../data-safety.md) sections 6.5 (step 4) and 9.

## What a spill is

On a forced quit with undurable records the writer spills them as a plain segment file (same
framing as the [WAL](wal.md)). At next start `import_all_spills(data_root)` picks them up.

## Discovery

`discover_spills` lists, in order and de-duplicated: `<data-root>/spill/*.wal`,
`<user-data-dir>/spill/*.wal` (`~/.local/share/sadi`, `%LOCALAPPDATA%\sadi`,
`~/Library/Application Support/sadi`) and `sadi-spill-*.wal` in the OS temp dir.

## Validation

`scan_spill` is read-only. It checks the segment header CRC, then every frame (magic,
CRC-32C over header and payload, dense seqs from the header's `first_seq`). The first bad
frame ends the verified prefix; the rest is reported as `SpillTail` (offset, length, SHA-256,
reason). Nothing is truncated. A bad header (`SpillHeaderInvalid`) or zero verified records
(`SpillEmpty`) imports nothing and creates no directory.

## Import

`import_spill` creates a NEW version dir (exclusive `mkdir`, never reused) and copies the
verified frames byte for byte (seq, timestamps and CRCs preserved) into `wal/seg-000001.wal`
under a fresh segment header, fsyncs, then re-verifies with `WalReader.scan`. If a session
manifest with the spill's session uuid exists, the import is the next version of that family
with `parent` and `parent_last_seq` set, and `ImportReport.continuity_ok` says whether seqs
continue; otherwise a new `spill-import` family is started.

The spill file is kept. A sidecar `<name>.imported.json` (SHA-256, target dir) is created
exclusively beside it so the same content is not imported at every start; if that cannot be
written, `marker_written` is false and a warning is logged.

The imported version has no `SESSION_START` (the spilled records are only the undurable
tail); it is a data-bearing version whose lineage is in its manifest.

### Join, overlap, provenance, space (audit-5 M1-M4)

- Join (M1): the spill may overlap the parent, `parent.first_seq <= spill.first_seq <=
  parent.last_seq + 1` (gap seqs must be SEALs). A failed fsync leaves the batch already written
  to the parent segment, so overlap is the normal case. Overlapping frames must be identical
  (type, wall_ns, flags, payload) or the spill is kept as a fragment. The joined WAL is the
  parent's records plus the spill records beyond the parent's last seq, renumbered densely
  (SEALs dropped; see the L2 followup: raw-seq references shift after a rotation).
- Supersede (M2): the new manifest has `spill_import = "joined"` or `"fragment"`.
  `routes/sessions.py` lets only a `joined` import in state `closed` supersede an incomplete
  parent; fragment and crashed imports never do.
- Provenance (M3): the import inherits the parent's synthetic flag/marker. An orphan spill has
  no provenance: the manifest bool cannot say "unknown", so it stays set (never labelled real)
  and the setup list shows an orphan (no parent, `spill_import` set) as "Provenance unknown".
- Space and failure (M4): before joining, free space must cover the parent WAL size plus the
  spill plus 64 MiB, else the spill is imported as a fragment (WARNING "join deferred"). If the
  join write fails anyway, the partial dir is kept (state `crashed`), a sidecar
  `<name>.join-failed.json` names it, the spill is imported as a fragment, and later starts
  never attempt the join again for that content. Nothing is deleted or overwritten.
- Verify before close: the joined segment is re-scanned before the version is closed. A failed
  re-read marks it `crashed` (kept), writes the failed-join marker and imports the fragment.
  An exclusive `<name>.join-inprogress.json` is created before the join copy, so a join killed
  mid-copy is also never retried (fragment instead).
- Lineage: `_descendants` does not walk through a non-superseding spill import, so resuming a
  fragment never marks the full parent as superseded. The setup list labels fragments
  ("Recovered fragment ...") and joined imports ("Recovered (complete)").

## Startup

`sadi.server.app._lifespan` calls `import_all_spills` right after the data-root lock is held
and before the app serves. Each import is logged at WARNING (recovered), already-imported
spills at INFO. A failed spill is logged at ERROR with the file left intact; startup
continues and `app.state.spill_failures` holds the failure count. Spills are never deleted
or overwritten. Without the lock (degraded mode) no import is attempted.
