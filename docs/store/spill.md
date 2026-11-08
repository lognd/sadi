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
