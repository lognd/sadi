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
- Budgets come from an injected `AppSettings.budgets` callable; build entries with
  `to_result_budget(result, label, Budget, latex)` from `Uncertain.budget` and `Uncertain.latex`.
  Until a lab supplies one the list is empty (follow-up).
- The lctt `recompute` is a stub, so `values` is empty today; captured points are passed with
  zeroed time fields because the point wire shape carries none.
- Device status reads an injected `AppSettings.device` (a `DeviceService`); without one the
  response is `attached=false, status=error` with a hint.
- `GET /api/results` also returns `provenance`: one `QuantityProvenance` per value (`name`,
  `point_ids`, `first_sample`, `last_sample`, `algorithm`). Point ids and sample span are those of
  the active (non-excluded) points fed to `recompute`; `algorithm` is `<lab>.recompute`. It is
  empty while the lctt recompute is a stub.
