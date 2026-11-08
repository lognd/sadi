# Server app factory

Status: current

`sadi.server.app.create_app(settings)` builds a fresh FastAPI app with no global state.
It mounts `make_doctor_router()` (`/api/doctor`, see [doctor-ui.md](../web/doctor-ui.md))
and `make_plugins_router(registry)` (`/api/plugins`).

`AppSettings` (pydantic, frozen) is the injection point: `registry` (a `PluginRegistry`,
default empty) and `data_root` (a `Path`, default `data`). The settings are stored on
`app.state.settings`. Unknown paths return HTTP 404. No static web mount or launcher yet.

## Data-root lock

The app lifespan takes the exclusive data-root lock (`sadi.store.lock.acquire`) on
`data_root`, holds it for the process lifetime and releases it on shutdown. A live or
stale lock is never stolen (`recover_stale=True` is the explicit takeover). When refused,
startup raises `RootLockStartupError` (wrapping a typed `RootLockFailed`), so uvicorn
exits non-zero. With `require_root_lock=False` the app starts degraded and
`GET /api/root-lock` returns `{ok: false, kind, hint}`.
