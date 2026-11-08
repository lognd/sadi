# REST API: results, guidance, device status

Status: current

Router `sadi.server.routes.results.make_results_router` (mounted by `create_app`) adds four
read-only endpoints. Errors are problem+json with a `hint`, like [api.md](api.md).

| Endpoint | Returns |
| --- | --- |
| `GET /api/results` | `ResultSet` recomputed live from the open session via the lab's `recompute` |
| `GET /api/results/budgets` | `ResultBudget[]` (shape of `web/src/components/budget/types.ts`) |
| `GET /api/results/guidance?phase=&hold=&target=` | `GuidanceState` from `sadi.labs.lctt.guidance.guide` |
| `GET /api/device/status` | `DeviceView` (`status`, `attached`, `fault`, `hint`) |

- Results, budgets and guidance need an open session (409 `no_open_session` otherwise).
- `phase` is `calibrate|elastic|plastic` (default `calibrate`); a bad `phase` or non-positive
  `target` is a 422 problem. Guidance never changes the phase; it only proposes.
- Budgets come from an injected `AppSettings.budgets` callable when set; otherwise from the
  open session's lab if it implements the optional `sadi.core.lab.BudgetedLab` protocol
  (`budgets() -> list[LabBudget]`, each a result id, label, `Budget` and LaTeX). The route
  wraps them with `to_result_budget`. A lab without the hook yields an empty list.
- The lctt lab supplies nominal `stress` and `E` (chord modulus) budgets built with the public
  uncertainty engine (`sadi.labs.lctt.budgets.nominal_budgets`) at representative inputs, not
  from live session data, until its `recompute` is real.
- The lctt `recompute` is a stub, so `values` is empty today; captured points are passed with
  zeroed time fields because the point wire shape carries none.
- Device status reads an injected `AppSettings.device` (a `DeviceService`); without one the
  response is `attached=false, status=error` with a hint.
- `GET /api/results` also returns `provenance`: one `QuantityProvenance` per value (`name`,
  `point_ids`, `first_sample`, `last_sample`, `algorithm`). Point ids and sample span are those of
  the active (non-excluded) points fed to `recompute`; `algorithm` is `<lab>.recompute`. It is
  empty while the lctt recompute is a stub.

- `PointView` (session points, which feed these routes) carries `settled` and `forced_early`
  booleans copied from the captured `PointV1`; they are the operator-supplied capture flags
  and default to false for points recorded without them.
