# REST API: sessions, wizard, points

Status: current

Handlers in `sadi.server.routes.sessions` are thin and synchronous (`def`, so FastAPI runs
them in the threadpool and the event loop stays free). All logic lives in
`sadi.server.service.SessionService`, which reuses the session layer (`create_session_in_held_root`,
`resume_session_in_held_root`), `WriterHandle`, `recover_state` and the core `Wizard`.

## Data safety

- Every write is a WAL record, durable (`wait_durable`) before the response is sent.
- Undo/redo/edit are compensating records; nothing is deleted or overwritten.
- One session is open per server process; opening another gives 409 until `close`.
- Resume creates a NEW version with a parent link; the parent is never modified. The new
  version starts a fresh WAL (the parent's state is not folded in; follow-up ticket).
- The app holds the data-root flock, so session create/resume use the `*_in_held_root`
  variants, which do not take the lock again.

## Endpoints (prefix `/api`)

| Method and path | Purpose |
|---|---|
| GET `/labs` | registered labs |
| GET `/sessions` | session versions on disk (manifests only) |
| POST `/sessions` | create and open (`lab`, `slug`, `specimen`) |
| POST `/sessions/resume` | resume `name` as a new version |
| GET `/session`, POST `/session/close` | open session info; close |
| GET `/session/wizard` | rail and current step |
| POST `/session/wizard/complete`, `/skip`, `/revert` | step transitions |
| GET/POST `/session/points` | list; capture (typed inputs per phase) |
| POST `/session/points/{id}/edit` | edit (original kept in log) |
| POST `/session/undo`, `/redo`; GET `/session/history` | compensating edits |

Writes return `Committed {seq, summary, wizard, history}`.

## Errors

Every failure is `application/problem+json` with `type`, `title`, `status`, `detail` and a
`hint` saying what to do (`sadi.server.routes.problem`). Typed errors map by family
(device 503, input 422, store 500, compute 422, job 409; wizard errors 404/409/422), no
session open is 409, and malformed bodies are 422.

## Not yet (subset of ticket X3H80G2)

Inventory, results, guidance, export, device status, OpenAPI/TS client generation and the
loop-lag test are tracked as follow-up tickets.
