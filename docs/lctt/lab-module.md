# LCTT lab module and two-specimen workflow

Status: current

Owner: ~XMK16Q2. Code: `python/sadi/labs/lctt/lab.py`, `specimens.py` (registered by
`plugin.py`). Tests: `python/tests/labs/lctt/test_lab.py`.

The lctt [plugin](../plugins.md) contributes one `LabModule` ([contract](../core/lab-modules.md)).
`plugin.register()` returns `lab.LcttLab`; nothing in core names LCTT.

## Steps and phases

| Step | Phase | Capture |
| --- | --- | --- |
| Setup (clamp-slip check) | setup | device points |
| Calibrate (LVDT) | (a) calibration | device points |
| Tare | tare | device points |
| Elastic (long specimen) | (b) elastic | device points |
| Plastic (short specimen) | (c) plastic | device points |
| Results | results | none |
| Export | export | none |

There is no weights step in this lab: a weights/height inventory is supplied by whatever
plugin provides one. Calibration heights and experiment masses arrive as the core typed
inputs (`CalibrationInputs.height`, `LoadInputs.mass_kg`), so swapping the weights between
calibration and experiment needs no re-entry in the lab.

## Specimens

`SpecimenSpec(role, label, l0)`: role `elastic` (long, default L0 0.5 m, editable) or
`plastic` (short, default L0 0.08313 m, editable). `make_spec` / `with_l0` return
`Result[SpecimenSpec, SpecimenError]` and reject non-finite or non-positive L0.

## Combined results

`combine_runs(elastic_run, plastic_run, shared)` recomputes each run with the
[live engine](live-results.md) (gauge length from its spec) after the shared calibration and
tare inputs, then reports:

- `E` and `r2` from the long (elastic) specimen,
- `yield_stress` from the short (plastic) specimen.

Each `SourcedValue` carries the `ResultValue`, the specimen role, its name and its L0, so the
report states which specimen supplied each number. Results not yet computable are listed in
`pending`. Wrong roles give `LabError.WrongRole`.

## Core recompute

`LcttLab.recompute(points)` is pure. It uses the `volts`, `volts_sd` and `load_kg` carried on each
`CapturedPoint`; points missing volts or load are skipped and logged (never dropped from the
input), and no usable point gives `Err(ComputeError(TOO_FEW_POINTS))`. For the last usable point
it returns `stress` (always, from `LoadingContext` geometry, nominal 6 mm diameter by default),
and `strain` plus `secant_modulus` when the context supplies the calibration `slope_m_per_v` and
`tare_v`. All maths goes through the public uncertainty engine (`loading`, `modulus`).

## Session wiring

`LcttLab.analyze(points, inputs)` implements `sadi.core.lab.InputsAwareLab`. It derives a
`LoadingContext` with `context_from_inputs` (last specimen diameter and hanger, last tare, slope
fitted from three or more calibration points, gauge length from the last load phase), runs
`recompute` under it, and when both `elastic` and `plastic` load runs exist adds `E`, `r2` and
`yield_stress` from `combine_runs`. The server calls it through `session_points.analyze` for both
results and export. It is pure; raw events are never rewritten.

## Known gaps

Short-specimen `short-data.csv` is slip-affected and is not used to validate E. A bare `LcttLab()` still uses nominal geometry; the server supplies the real context via `analyze`.
