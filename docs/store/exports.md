# Derived exports with provenance

<!-- frob:waive DOC007 docs/index.md is leased by another ticket; link filed as follow-up -->

Status: current

Owner: ~36JQFXT. Code: `python/sadi/store/exports.py`. Tests: `python/tests/store/test_exports.py`.
Design: [data-safety.md](../data-safety.md) section 9.3; invariants I4, I5, I7.

## Contract

- `write_export(session, kind, basename, ext, payload, ...)` publishes
  `exports/<kind>/<NNNN>-<YYYYMMDDTHHMMSSZ>-<basename>.<ext>` plus a sidecar
  `<same>.prov.json`. `NNNN` is one more than the highest existing number.
- Atomic: the bytes go to a dot-prefixed exclusive tmp file, are fsynced, then renamed with
  `rename_noreplace` (which fsyncs the directory). The sidecar is written the same way.
- Never overwrites: a name collision takes the next number; a leftover tmp is never deleted.
  `kind` and `basename` are sanitised (`sadi.store.names`), `ext` must be `[A-Za-z0-9]{1,16}`.
- Provenance (`ExportProvenanceV1`): `sha256`, `size`, `created`, `covers_seq`, `prefix_hash`
  (data-safety.md 9.2, of the verified WAL, or of an explicit `covers_seq`), `snapshot_path`,
  `code_version`, `lab_module`, `parameters`.
- An export without a sidecar (crash between the two renames) is listed by `list_exports` as
  `complete=False` and must not be trusted; it is not removed.
- Optional `ref_sink` receives an `EXPORT_REF` record; failure there is logged only.
- Errors are `ExportError` (`BadName`, `Io`, `Wal`, `Ahead`, `NoFreeName`); details are logged.

## Regeneration

Exports are derived (I7): deleting `exports/` loses nothing. The regeneration test replays the
WAL, deletes `exports/`, writes the export again and asserts byte-identical data and identical
`sha256`/`prefix_hash`, with the WAL untouched.

## Failpoints

`export.mkdir`, `export.data.write`, `export.data.fsync`, `export.rename`,
`export.sidecar.write`, `export.sidecar.fsync`, `export.ref`.
