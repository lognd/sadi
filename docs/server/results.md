# REST API: results, guidance, device status

Status: current

Router `sadi.server.routes.results.make_results_router` (mounted by `create_app`) adds four
read-only endpoints. Errors are problem+json with a `hint`, like [api.md](api.md).

| Endpoint | Returns |
| --- | --- |
| `GET /api/results` | `ResultSet` recomputed live from the open session via the lab's `recompute` |
| `GET /api/results/budgets` | `ResultBudget[]` (shape of `web/src/components/budget/types.ts`) |
| `GET /api/results/guidance?phase=&hold=&target=` | `GuidanceState` from `sadi.labs.lctt.guidance.guide` |
| `GET /api/device/status` | `DeviceView` (`status`, `attached`, `fault`, `hint`, `stop_reason`, `acquisition_fault`); `disconnected` = no board attached; `stop_reason` is finished/idle/low_disk/no_device once raw streaming stopped |
| `POST /api/results/finish` | Not called by the web UI (it never posts here): `LiveAcquisition.finish()` drains raw blocks into the WAL and stops streaming (idempotent; session stays open, nothing deleted); returns `DeviceView`. Session close calls it too; `GET /api/export/{fmt}` never does (export is read-only on acquisition, even when it fails, so a mid-run export cannot end recording) |
| `POST /api/device/reconnect` | Reopens the board and resumes recording into the open session; returns `DeviceView`, 409 on failure |

- Results, budgets and guidance need an open session (409 `no_open_session` otherwise).
- `phase` is `calibrate|elastic|plastic` (default `calibrate`); a bad `phase` or non-positive
  `target` is a 422 problem. Guidance never changes the phase; it only proposes.
- Run phase owner: `SessionService.run_phase()` / `enter_phase()` (`sadi.server.run_phase`) hold
  the live run's phase. Entering a phase appends a `run.phase` MARKER (label = phase) to the
  session WAL, so it is append-only, durable, survives resume and is copied by resume folding.
  Only the next phase in order (calibrate, elastic, plastic) is legal; the fold ignores any
  out-of-order marker. REST: `GET/POST /api/session/run-phase`.
- The WS guidance provider (`make_guidance_provider`) reads the recorded phase, so plastic is
  sent once entered. Only sessions with no recorded phase (old data) fall back to inference:
  calibrate until a load point exists, then elastic. `GET /results/guidance` still honours its
  explicit `phase` query parameter.
- Budgets come from an injected `AppSettings.budgets` callable when set; otherwise from the
  open session's lab if it implements the optional `sadi.core.lab.BudgetedLab` protocol
  (`budgets() -> list[LabBudget]`, each a result id, label, `Budget` and LaTeX). The route
  wraps them with `to_result_budget`. A lab without the hook yields an empty list.
- The lctt lab supplies nominal `stress` and `E` (chord modulus) budgets built with the public
  uncertainty engine (`sadi.labs.lctt.budgets.nominal_budgets`) at representative inputs, not
  from live session data, until its `recompute` is real.
- Results and export share one recompute path, `session_points.analyze(lab, views)`: a lab that
  implements the optional `sadi.core.lab.InputsAwareLab` hook (`analyze(points, inputs)`) also
  sees the typed session inputs. For lctt these give a `LoadingContext` (specimen diameter and
  hanger mass, last tare, slope fitted from three or more calibration points), so `values`
  include `strain` and `secant_modulus` once tare and calibration exist; with both elastic and
  plastic runs captured `combine_runs` adds `E`, `r2` and `yield_stress`. Until then (or if the fit fails) `E`, `r2` and `yield_stress` are listed in
  `pending` with a `notes` entry saying what is missing. Too few usable points
  is an empty result with a note. The recompute is pure; stored events are never rewritten.
- Device status reads an injected `AppSettings.device` (a `DeviceService`); without one the
  response is `attached=false, status=error` with a hint.
- `GET /api/results` also returns `provenance`: one `QuantityProvenance` per value (`name`,
  `point_ids`, `first_sample`, `last_sample`, `algorithm`). Point ids and sample span are those of
  the active (non-excluded) points fed to `recompute`; `algorithm` is `<lab>.recompute`. It is
  empty until the session has usable load points.

- `PointView` (session points, which feed these routes) carries `settled` and `forced_early`
  booleans copied from the captured `PointV1`; they are the operator-supplied capture flags
  and default to false for points recorded without them.
