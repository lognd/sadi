# Server app factory

Status: current

`sadi.server.app.create_app(settings)` builds a fresh FastAPI app with no global state.
It mounts `make_doctor_router()` (`/api/doctor`, see [doctor-ui.md](../web/doctor-ui.md))
and `make_plugins_router(registry)` (`/api/plugins`).

`AppSettings` (pydantic, frozen) is the injection point: `registry` (a `PluginRegistry`,
default empty) and `data_root` (a `Path`, default `data`). The settings are stored on
`app.state.settings`. Unknown paths return HTTP 404. The `sadi` launcher ([launcher.md](launcher.md)) mounts the built web assets.

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
reads Saved with nothing pending.

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

When `settings.curve_source` is None, `create_app` injects `sadi.server.curve_source.make_curve_source(data_root)`.
The active session is the newest directory (names sort by UTC stamp) under
`<data_root>/sessions` that has a `wal/`. Each call recovers its state read-only
(`sadi.store.events.recover_state`: snapshot plus WAL tail, no repair, no writes), maps POINT
events by `phase` (`calibration`: volts, height; `tare`: mean, sd, n; `specimen`: diameter,
u_diameter, hanger_kg, u_hanger_kg; any other phase is a load point: volts, mass_kg and
optional u_volts, u_mass_kg; defined once in `sadi.core.point_inputs`, which the recording
path also uses to write them), derives the curve with `build_document` and returns the
non-excluded points. No session, replay failure or an unready session gives 409 `NoData`.
