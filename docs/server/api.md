# REST API: sessions, wizard, points

Status: current

Handlers in `sadi.server.routes.sessions` are thin and synchronous (`def`, so FastAPI runs
them in the threadpool and the event loop stays free). All logic lives in
`sadi.server.service.SessionService`, which reuses the session layer (`create_session_in_held_root`,
`resume_session_in_held_root`), `WriterHandle`, `recover_state` and the core `Wizard`.

Live data (trace frames, state, results) is pushed over a WebSocket: [websocket.md](websocket.md).

Related REST surfaces: [results.md](results.md), [export.md](export.md) and [plots.md](plots.md).

## Data safety

- Every write is a WAL record, durable (`wait_durable`) before the response is sent.
- Undo/redo/edit are compensating records; nothing is deleted or overwritten.
- One session is open per server process; opening another gives 409 until `close`.
- Resume creates a NEW version with a parent link; the parent is never modified. The new
  version's WAL starts by folding the parent's POINT, EDIT, SETTINGS and MARKER records in
  their original order (raw capture data stays in the parent); the parent stays byte-identical.
  See `_fold_parent` in `sadi.server.service`.
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
| GET/POST `/session/run-phase` | recorded guided-run phase; POST enters the next phase only (409 otherwise) |

Writes return `Committed {seq, summary, wizard, history}`.

## Errors

Every failure is `application/problem+json` with `type`, `title`, `status`, `detail` and a
`hint` saying what to do (`sadi.server.routes.problem`). Typed errors map by family
(device 503, input 422, store 500, compute 422, job 409; wizard errors 404/409/422), no
session open is 409, and malformed bodies are 422.

## Not yet (subset of ticket X3H80G2)

Inventory, results, guidance, export, device status, OpenAPI/TS client generation and the
loop-lag test are tracked as follow-up tickets.

## POST /api/session/load-change

`sadi.server.routes.acquisition` calls `LiveAcquisition.mark_load_change`, which records a WAL
MARKER (`load_applied`) through the live pipeline and returns `{marker_seq}`. 409
`no_live_session` when no acquisition runs; 409 `acquisition_halted` when the pipeline refuses.

## POST /api/acquisition/resume

`LiveAcquisition.resume` restarts raw streaming after an idle pause (`stop_reason == "idle"`)
without writing a load-change MARKER and without the simulator's extra load step. Response
`{streaming: true}`; idempotent while streaming. 409 `no_live_session` for a finished, low-disk,
no-device or absent run. The UI button ("Resume live readings") is a follow-up; the web client does
not call it yet. If the device stop command fails (cable pulled), `AcquisitionDriver.stop` still
ingests the blocks already drained (`StopFailed.blocks`) before reporting the fault, and a
reconnect teardown keeps queued blocks (`DeviceService.take_salvaged`) and writes them to the WAL.

## Capture validation and completion gates

`POST /session/points` is checked before anything reaches the WAL, and a rejection writes nothing.
All checks answer 422 `urn:sadi:error:input:<code>`: `missing` (required field absent or not
finite), `out_of_range` (`core.point_inputs.check_ranges`: every value finite and inside a
physical range in SI units, e.g. diameter 0.05..5 mm, heights 0..1 m; a value that looks like mm
gets "did you mean ..." in the message) and `bad_window` (`check_window`: seqs and sample offsets
non-negative, first not after last). Limitation: the server has no raw index, so it does not
re-derive volts from the window nor require the window to point at durable RAW_BLOCK records.

`POST /session/wizard/complete` consults the step's `complete_check` (`StepSpec`) and answers 422
`step_quality_gate` if it fails: `calibrate` needs a valid `fit_calibration`, and `setup` is
blocked while the clamp-slip check has failed (repeat it, or skip the step explicitly).
