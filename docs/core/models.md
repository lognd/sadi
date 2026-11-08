# Core models and error taxonomy

Status: current

Owner: ~FY28A3R. Code: `python/sadi/core/models.py`, `python/sadi/core/errors.py`.
Tests: `python/tests/core/test_models.py`.

## Units

All numeric fields are SI internally: m, kg, s, N, Pa, V (and derived
`m/V`, `m^2`). `Quantity.unit` is validated against an SI symbol set; there
is no conversion code in the models. Conversion (mm, MPa, GPa, ...) happens
only at display time, in the formatter (~M27Y4NY) and the UI.

## Models (frozen pydantic, JSON round-trip tested)

| Model | Fields |
|---|---|
| `Quantity` | `value`, `standard_uncertainty` (>= 0, 95 %), `unit` |
| `Specimen` | `id`, `l0`, `diameter` (m), `description`; `area` property (pi d^2 / 4) |
| `TimeWindow` | `start`, `end` (s since run start) |
| `PointEdit` | `field`, `old`, `new`, `at` |
| `CapturedPoint` | `index`, `window`, `t_since_load`, `drift_rate`, `status` (`settled` / `forced_early`), `edits`, optional `volts`, `volts_sd`, `load_kg` (default `None`; old data loads unchanged) |
| `Phase` | `setup`, `calibration`, `tare`, `elastic`, `plastic`, `results`, `export` |
| `RunState` | `session_id`, `phase`, `specimen`, `tare`, `points`, `events` (opaque raw lab events for export writers); `advance`, `with_point` return copies |

Models are immutable; updates return new values so replay from the event
log is deterministic. Constructors raise pydantic `ValidationError` for
malformed data (a programmer or wire-format bug); fallible lookups and
edits return typani `Result`.

## Error taxonomy

Errors are frozen pydantic values used as the `E` in `Result[T, E]`.
Families: `DeviceError`, `InputError`, `StoreError`, `ComputeError`,
`JobError`, each with a typani `ErrorSet` of codes (`DeviceCode`, ...). Member names
are UPPER_SNAKE; the wire value (problem `type`, stored data) is
`wire(code)`, the lowercase name, and `code_from_wire(family, s)` reverses it. Every code
has a user-facing "what to do" hint (`SadiError.hint`, `hint_for(code)`);
a test asserts the table is complete.

`SadiError.problem()` returns the RFC 7807 body used by the HTTP layer:
`type` (`urn:sadi:error:<family>:<code>`), `title`, `status`, `detail`,
`hint`. Status by family: device 503, input 422, store 500, compute 422,
job 409.

```python
from typani import Err
from sadi.core.errors import DeviceCode, DeviceError

return Err(DeviceError(code=DeviceCode.DISCONNECTED, detail="port closed"))
```

### StrEnum vs ErrorSet audit (PYEFC79)

Error families (failures returned as `Err`) are `ErrorSet`: `DeviceCode`,
`InputCode`, `StoreCode`, `ComputeCode`, `JobCode`. The writer-thread
errors (`WriterError` subclasses) carry a `code: StoreCode` and convert
with `to_store_error()`.

Kept as `StrEnum` because they are states, modes or labels, not errors:
`ErrorFamily` (discriminator), `JobState`, `Outcome`, `ResultState`,
`DeviceStatus`, `WriterState`, `McStatus`, `Notation`, `SettleState`,
`SettleMode`, `SettleStatus`, `SaveState`, `StepStatus`, `PluginState`,
`Phase`, `Severity`, `CaptureKind`, `CaptureMode`, `Marginal`,
`SettleSource`, `VoltageUncertainty`, `SignPolicy`, `Specimen`.
`NotSettledReason` is a reason label on a non-error result and also stays.
