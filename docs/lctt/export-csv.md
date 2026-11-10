# LCTT CSV export (49-column schema)

Status: current

Owner: ~7P8582F. Code: `python/sadi/labs/lctt/export_csv.py`. Tests: `python/tests/labs/lctt/test_export_csv.py`.
Format source: [domain.md](../domain.md) section 4; byte policy: [store/csv-export.md](../store/csv-export.md).

## Layout

Metadata rows (`key,value`: Title, Schema, Date, Operator, Description, tare, calibration,
specimen inputs, modulus fit, yield), one blank line, the 49-column header, one row per logged
point (including excluded ones, flagged). Columns are the fields of `PointRow`, in order:
`point_id, index, phase, elapsed_s, volts, u_volts, volts_sd, mass_kg, u_mass_kg, delta_volts, u_delta_volts, height_m, displacement_m, u_displacement_m,
load_n, u_load_n, area_m2, u_area_m2, stress_pa, u_stress_pa, strain, u_strain,
secant_modulus_pa, u_secant_modulus_pa, hanger_kg, u_hanger_kg, total_mass_kg, offset_line_pa, excluded, in_window, saturated,
settle_source, is_yield, is_ultimate, low_r2, warnings, slope_m_per_v, tare_v, u_tare_v, l0_m, u_l0_m, diameter_m, u_diameter_m,
intercept_m, u_intercept_m, hanger_n, u_hanger_n, mass_n, u_mass_n`.

Reference comparison: a private mapping of these columns and metadata keys against the original
lab VI export exists in the gitignored private tree (not linked from tracked files); the names
above remain this project's own definition. Structural differences found: `PointRow` now
carries the reference's elapsed-time, per-sample standard deviation and per-quantity uncertainty
columns; the reference repeats session constants
(calibration, tare, gauge length, diameter) on every row where this project keeps them in the
metadata block; it expresses loads in force units where `PointRow` uses mass; column order differs;
and `PointRow` adds selection and flag columns (id, index, window, exclusion, yield, ultimate,
saturation, warnings). The reference metadata also stores raw calibration points and per-input
reading statistics, which the metadata block here does not. Any change to `PointRow` is tracked
as a separate ticket (decision below); reader, writer and tests follow its field order.

`elapsed_s` is seconds since the load was applied (from the capture settle record) and `volts_sd`
is the per-sample standard deviation of the raw volts in the averaging window (`u_volts` is the
standard error of the mean); both are `NaN` when unknown (older sessions, single-sample windows).
Uncertainty columns (schema `3`) are the engines' propagated standard uncertainties, not new
estimates: `u_tare_v` is the standard error of the pooled tare mean, Sx/sqrt(N) (the same model as the Results `tare`); every row uses this one model: `u_strain`, `u_stress`, `u_delta_volts` and `u_displacement_m` all take U_tare = Sx/sqrt(N), so `u_strain` is approximately `u_displacement_m / l0_m` (stated in the `Row uncertainty model` metadata line); `u_delta_volts = hypot(u_volts, u_tare_v)`;
`u_displacement_m` propagates delta volts and the calibration slope; `u_hanger_kg` and `u_diameter_m`
are the specimen inputs; `u_l0_m` is `0` (gauge length is an exact configured constant);
`u_secant_modulus_pa` is quotient propagation of stress and strain (independent inputs), `NaN`
when strain is zero. `diameter_m` is added beside its uncertainty.
Schema version is `5` (3 added uncertainty columns; 4 adds the six below; 5 adds the `phase` column); the reader requires the exact header, so version-1 and
version-2 files are rejected with `BadHeader`.

Raw calibration points are stored in the metadata block as numbered rows `Cal point N volts (V)`
and `Cal point N height (m)` (N from 1, after `Cal n`). `to_live_events` rebuilds one `CalPoint`
per consecutive pair (stopping at the first gap), so a file can be fully re-analysed. This adds
metadata rows only, the 49-column header is unchanged, so it did not bump the schema; files without the
rows still read and simply yield no `CalPoint`.

Numbers: 10 significant digits, `.` decimal, `NaN`, `Inf`, `-Inf` literal; booleans `1`/`0`.

## Decision: reference session constants and force units (~437XJK7)

Lose no information, keep both representations; no column is removed or renamed. Slope, tare,
gauge length, diameter and hanger mass were already repeated on every row; schema `4` appends
`intercept_m`, `u_intercept_m` (calibration intercept and its standard error), `hanger_n`,
`u_hanger_n` (hanger weight as force, `hanger_kg * g`) and `mass_n`, `u_mass_n` (inventory-mass
weight as force, `mass_kg * g`, excluding the hanger). `load_n` is already the total force. `g` is
the standard 9.80665 m/s^2, treated as exact (no added uncertainty). Cells are always known for an
exportable session (calibration, tare, specimen are required). Version 3 files are rejected with
`BadHeader`, as with earlier bumps.

## Derivation and writing

`build_document(events, date=...)` replays raw live events (never cached display values) through
the calibration, loading, modulus and yield engines; the CSV is derived (I7), never the source
of truth. `export_csv(session, events, ...)` publishes through `store.exports.write_export`:
kind `lctt-csv`, numbered name, sanitised basename (`sanitize_name`), tmp + fsync + no-replace
rename, provenance sidecar. An existing export is never overwritten (next number is taken).

## Web export format

`LcttLab.export_formats` declares `lctt-csv` (`CSV_FORMAT`, `text/csv`). Its writer takes the raw
events from `RunState.events`, runs `build_document` and returns `render_document` bytes in
memory (read-only; the numbered on-disk `export_csv` is a separate path). An unready session
(no calibration, tare, specimen or points) yields a compute error, not an empty file.

## Reader

`read_document` / `read_file` parse a file back to `CsvDocument` (metadata + typed rows), and
`to_live_events` rebuilds tare, specimen, point, exclusion and window events for
post-processing (Q1). Calibration points are not in the file, only the fit.

## Encoding and line endings

Writer: UTF-8, no BOM, CRLF after every row including the last, identical on every OS (bytes
built in memory and written through a binary fd; no text-mode translation). Reader: accepts
CRLF or LF and an optional BOM; invalid UTF-8 is `Encoding`. `.gitattributes` pins `*.csv -text`.
Tests assert the exact bytes (no lone LF, no BOM, ASCII) and LF/BOM tolerance.

## Tests

Synthetic export -> read -> compare field by field always runs; the same check on the private
short-run file is skipped when `python/tests/fixtures/real_fp/` is absent.

## Phases (schema 5)

Each row carries its `phase` (`elastic`, `plastic`, or empty for legacy single-curve sessions). Rows
are grouped by phase and every group is fitted on its own gauge length: elastic uses 0.5 m, plastic
uses 0.08313 m, so `l0_m`, `in_window`, `saturated`, `is_yield` and `offset_line_pa` are per group.
E is fitted on the elastic group (the explicit window addresses it); yield is computed only on the
plastic group using that group's own modulus. Metadata `E` comes from the elastic group and yield
from the plastic group, so CSV values equal `/api/results`. Metadata `Specimen L0 (m)` is replaced by
`Elastic L0 (m)` and `Plastic L0 (m)`.
