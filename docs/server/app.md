# Server app factory

Status: current

`sadi.server.app.create_app(settings)` builds a fresh FastAPI app with no global state.
It mounts `make_doctor_router()` (`/api/doctor`, see [doctor-ui.md](../web/doctor-ui.md))
and `make_plugins_router(registry)` (`/api/plugins`).

`AppSettings` (pydantic, frozen) is the injection point: `registry` (a `PluginRegistry`,
default empty) and `data_root` (a `Path`, default `data`). The settings are stored on
`app.state.settings`. Unknown paths return HTTP 404. No static web mount or launcher yet.
