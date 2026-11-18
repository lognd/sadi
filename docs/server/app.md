# Server app factory

Status: current

`sadi.server.app.create_app(settings)` builds a fresh FastAPI app with no global state.
It mounts `make_doctor_router()` (`/api/doctor`, see [doctor-ui.md](../web/doctor-ui.md))
and `make_plugins_router(registry)` (`/api/plugins`).
`make_health_router()` serves `GET /api/health` -> `{status: "ok", version, simulated}`; it needs no
session (never 409). `simulated` is null unless `AppSettings.device` is set.

`AppSettings` (pydantic, frozen) is the injection point: `registry` (a `PluginRegistry`,
default empty) and `data_root` (a `Path`, default `data`). The settings are stored on
`app.state.settings`. Unknown paths return HTTP 404. The `sadi` launcher ([launcher.md](launcher.md)) mounts the built web assets.

`AppSettings.bus` (a pipeline `Bus`) optionally enables `WS /api/stream`; see [websocket.md](websocket.md).
`AppSettings.live` (a `LiveAcquisition`, see `sadi/server/live.py`) binds a per-session acquisition
pipeline to the session writer through `SessionService.set_hooks`: it starts after a session opens
and is stopped (tail drained into the WAL) before the writer closes. Samples always go through the
session WAL. With no session open nothing is streamed or recorded.

## Data-root lock

The app lifespan takes the exclusive data-root lock (`sadi.store.lock.acquire`) on
`data_root`, holds it for the process lifetime and releases it on shutdown. A live or
stale lock is never stolen (`recover_stale=True` is the explicit takeover). When refused,
startup raises `RootLockStartupError` (wrapping a typed `RootLockFailed`), so uvicorn
exits non-zero. With `require_root_lock=False` the app starts degraded and
`GET /api/root-lock` returns `{ok: false, kind, hint}`.

## Save indicator

`create_app` mounts `make_save_indicator_router` (`GET /api/save-indicator`, see
`sadi.api.save_indicator`). `AppSettings.writer` optionally injects the `WriterHandle`
(any `FailableSeqSource`); the app builds one `SaveIndicator` over it (kept on
`app.state.save_indicator`) and registers `SaveIndicator.mark_failed` via
`writer.on_failure`, so a writer failure latches NOT SAVED. With no writer the indicator
follows the open session's real writer: `create_app` hooks session open/close
(`SessionService.set_hooks`, chained with the live-acquisition hooks), binds the indicator's seq
source to the new `WriterHandle` and registers `mark_failed` on it, so Saving (pending seqs) and
NOT SAVED reflect the real WAL. With no session open nothing is pending and it reads Saved.

## Stress-strain refit

`create_app` mounts `make_stress_strain_router(settings.curve_source)`
(`sadi.server.routes_stress_strain`): `POST /api/stress-strain/fit`, called by
`web/src/api/refit.ts`. It is read-only: each call re-reads the curve through the injected
`CurveSource` (`() -> Result[Sequence[CurvePoint], RefitError]`) and refits with
`sadi.labs.lctt.modulus.fit_modulus`; nothing is written.

Request: `{"first": int, "last": int}`, an inclusive window of indices into the active
(non-excluded) curve; at least 3 points, `0 <= first < last < n`.

Response 200 (`ModulusFitView`): `first`, `last`, `modulusMpa` (slope, MPa), `interceptMpa`
(MPa), `display` ("E = x +/- y GPa, r^2 = z"), `eGpa`, `eU95Gpa` (U95 of E, GPa), `r2`, `lowR2`.

Errors are `{"error": <code>, "detail": <hint>}`: 422 `BadWindow` / `Fit` / `NoWindow`
(fix the window), 409 `NoData` (no `curve_source` or no stored data), 500 `Propagation` /
`Intercept`. A body missing `first` or `last` gets FastAPI's standard 422 validation body.

### Active session curve source

The source tails the session WAL incrementally (see `docs/store/incremental-replay.md`), so calls stay O(new records) while the simulator writes raw blocks; `SessionService.notes()` does likewise.

When `settings.curve_source` is None, `create_app` injects `sadi.server.curve_source.make_curve_source(data_root)`.
The active session is the newest directory (names sort by UTC stamp) under
`<data_root>/sessions` that has a `wal/`. Each call recovers its state read-only
(`sadi.store.events.recover_state`: snapshot plus WAL tail, no repair, no writes), maps POINT
events by `phase` (`calibration`: volts, height; `tare`: mean, sd, n; `specimen`: diameter,
u_diameter, hanger_kg, u_hanger_kg; any other phase is a load point: volts, mass_kg and
optional u_volts, u_mass_kg; defined once in `sadi.core.point_inputs`, which the recording
path also uses to write them; the POINT's settle meta - settled, forced_early, drift_rate, t_since_load_s - is read with `parse_meta`, defaults for older events, are carried onto each replayed `LoadPoint` as `settled`, `forced_early`, `drift_rate`, `t_since_load_s` via `session_events`, so the fit and results can see forced-early points; forced-early points are also logged; fit math is unchanged), derives the curve with `build_document` and returns the
non-excluded points. No session, replay failure or an unready session gives 409 `NoData`.

## Session routes

`create_app` also mounts the session/wizard/point router and installs the problem+json
handlers; see [api.md](api.md). `AppSettings.labs` injects the `LabRegistry` (default empty).

Results, budgets, guidance and device status routes: [results.md](results.md). `AppSettings.device` and `AppSettings.budgets` inject their sources.

Per-action state comes from `IncrementalReplay` (docs/store/incremental-replay.md), not a full WAL walk per request, so action latency stays flat as raw data accumulates.

`create_app` builds one `SessionReplayCache` and hands it to the export, plots and curve-source wiring, so all three share one `IncrementalReplay` per session (bounded to a few sessions; eviction only costs a verified full replay).

## Raw streaming lifecycle (audit2 H2b)

`LiveAcquisition` (`sadi/server/live.py`) stops writing raw device blocks to the WAL when it
should, without ever dropping recorded data: every block already read is drained into the WAL
before the device is stopped, and the session, writer and WAL stay open and untouched.

- `finish()` / `stop_streaming(reason)`: stop for a finished session (`stop_reason == "finished"`).
  A later load change is refused (`LiveError.Finished`); resume the session to record again.
- Idle: a watchdog thread (`WATCH_POLL_S`) pauses streaming after `IDLE_TIMEOUT_S` (600 s) with no
  load change, no unsettled point update and no result. A new `mark_load_change` restarts the
  stream on the same writer.
- Low disk: below `LIVE_MIN_FREE_BYTES` (1 GiB, `sadi.core.device.free_bytes`) the stream stops,
  `LiveAcquisition.fault` becomes `DriverFault(origin="disk")`, a `PipelineStopped(low_disk)`
  event goes to the bus, and new capture is refused (`LiveError.LowDisk`). A session opened under
  the floor starts no stream. Nothing is deleted; the writer's own 512/128 MiB guards still apply
  (docs/data-safety.md 6.5).

## Reconnect and no-board start (audit2 H8c)

With no board at start the launcher serves an unopened `DeviceService` (status `disconnected`).
`LiveAcquisition.on_session_open` then sets `stop_reason == "no_device"` (`STOP_NO_DEVICE`) and a
`DriverFault` instead of raising. `SessionService.set_capture_gate(LiveAcquisition.capture_block_hint)`
makes `capture` answer 409 `no_device` until a board is attached. `LiveAcquisition.reconnect_device()`
(behind `POST /api/device/reconnect`) reopens the device and, if a session is open and not finished
or low on disk, starts a run with a new SETTINGS record; the WAL is only ever appended to. It is a
no-op while a healthy run is active, and a failed open returns a 409 problem with the session intact.

`SessionService.finish_acquisition()` (wired by `set_acquisition`) calls `LiveAcquisition.finish()` on `POST /api/results/finish` and at close.
`GET /api/export/{fmt}` does not finish: it is read-only on acquisition and renders from what the WAL already holds.
`capture_block_hint` also refuses capture (409, plain hint) when `stop_reason` is finished, low_disk, idle or no_device. A finish fault is
logged and surfaced as `acquisition_fault` on `/api/device/status`; it is never raised and never discards WAL data.

`GET /api/design/next-weight` (`routes/design.py`) is read-only: it builds observations from active settled points and returns the advisory next weight plus the enough-data indicator; see [design/gp-selector.md](../design/gp-selector.md).

`POST /api/session/points` is idempotent per `request_id`. The POINT record stores a digest of the operator-chosen fields (`request_digest`), so after a reopen the replay fallback still compares it: the same id with a different body is a 409 `request_id_reused`, the same body returns "Already saved". Points written before the digest existed carry none and count as a match. The route declares 409 and 503 `ApiProblem` responses, and `DesignIndicator.reasons` is a closed enum (`ReasonCode`) in `openapi.json`.
