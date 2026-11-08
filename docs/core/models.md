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
| `CapturedPoint` | `index`, `window`, `t_since_load`, `drift_rate`, `status` (`settled` / `forced_early`), `edits` |
| `Phase` | `setup`, `calibration`, `elastic`, `plastic` |
| `RunState` | `session_id`, `phase`, `specimen`, `tare`, `points`; `advance`, `with_point` return copies |

Models are immutable; updates return new values so replay from the event
log is deterministic. Constructors raise pydantic `ValidationError` for
malformed data (a programmer or wire-format bug); fallible lookups and
edits return typani `Result`.

## Error taxonomy

Errors are frozen pydantic values used as the `E` in `Result[T, E]`.
Families: `DeviceError`, `InputError`, `StoreError`, `ComputeError`,
`JobError`, each with a `StrEnum` of codes (`DeviceCode`, ...). Every code
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
