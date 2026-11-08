# LCTT CSV export (42-column schema)

Status: current

Owner: ~7P8582F. Code: `python/sadi/labs/lctt/export_csv.py`. Tests: `python/tests/labs/lctt/test_export_csv.py`.
Format source: [domain.md](../domain.md) section 4; byte policy: [store/csv-export.md](../store/csv-export.md).

## Layout

Metadata rows (`key,value`: Title, Schema, Date, Operator, Description, tare, calibration,
specimen inputs, modulus fit, yield), one blank line, the 42-column header, one row per logged
point (including excluded ones, flagged). Columns are the fields of `PointRow`, in order:
`point_id, index, elapsed_s, volts, u_volts, volts_sd, mass_kg, u_mass_kg, delta_volts, u_delta_volts, height_m, displacement_m, u_displacement_m,
load_n, u_load_n, area_m2, u_area_m2, stress_pa, u_stress_pa, strain, u_strain,
secant_modulus_pa, u_secant_modulus_pa, hanger_kg, u_hanger_kg, total_mass_kg, offset_line_pa, excluded, in_window, saturated,
settle_source, is_yield, is_ultimate, low_r2, warnings, slope_m_per_v, tare_v, u_tare_v, l0_m, u_l0_m, diameter_m, u_diameter_m`.

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
as a separate ticket; reader, writer and tests follow its field order.

`elapsed_s` is seconds since the load was applied (from the capture settle record) and `volts_sd`
is the per-sample standard deviation of the raw volts in the averaging window (`u_volts` is the
standard error of the mean); both are `NaN` when unknown (older sessions, single-sample windows).
Uncertainty columns (schema `3`) are the engines' propagated standard uncertainties, not new
estimates: `u_tare_v` is the pooled tare uncertainty; `u_delta_volts = hypot(u_volts, u_tare_v)`;
`u_displacement_m` propagates delta volts and the calibration slope; `u_hanger_kg` and `u_diameter_m`
are the specimen inputs; `u_l0_m` is `0` (gauge length is an exact configured constant);
`u_secant_modulus_pa` is quotient propagation of stress and strain (independent inputs), `NaN`
when strain is zero. `diameter_m` is added beside its uncertainty.
Schema version is `3` (columns added); the reader requires the exact header, so version-1 and
version-2 files are rejected with `BadHeader`.

Numbers: 10 significant digits, `.` decimal, `NaN`, `Inf`, `-Inf` literal; booleans `1`/`0`.

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
