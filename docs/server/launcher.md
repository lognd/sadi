# Launcher (`sadi`)

Status: current

Console script `sadi` (`sadi.launcher:main`).

- `sadi serve` (also bare `sadi`, or `sadi --port N`): runs the doctor preflight
  read-only, then starts uvicorn on `create_app(AppSettings(data_root=...))`.
  Options: `--host` (default `127.0.0.1`), `--port` (8000), `--data-root` (`data`),
  `--web-dist` (`web/dist`), `--skip-preflight`.
- `sadi doctor ...`: passthrough to `sadi-doctor`.

Preflight: a doctor exit code of 2 (blocker) prints the doctor's step-by-step report
to stderr and exits 2 without starting. Nothing is auto-fixed. Exit 1 (problems) logs a
warning and starts.

Data-root lock: taken by the app lifespan; a refused lock (live or stale) is never
stolen, and the launcher exits 3 printing the lock hint.

Web: when `web/dist/index.html` exists, `mount_web` mounts it at `/` after the API routes
(so `/api/*` wins). Without it the API is served alone with a warning. The mount lives in
`sadi.launcher`, not in `app.py`.
