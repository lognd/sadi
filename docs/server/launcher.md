# Launcher (`sadi`)

Status: current

Console script `sadi` (`sadi.launcher:main`).

- `sadi serve` (also bare `sadi`, or `sadi --port N`): runs the doctor preflight
  read-only, then starts uvicorn on `create_app(AppSettings(data_root=...))`.
  Options: `--host` (loopback only, default `127.0.0.1`), `--port` (default 8000),
  `--data-root` / `--data-dir`, `--web-dist` (`web/dist`), `--skip-preflight`,
  `--no-browser`, `--sim`, `--selftest`, `--version`, `--allow-non-loopback` (UNSAFE).
- `sadi doctor ...`: passthrough to `sadi-doctor`.

Preflight: a doctor exit code of 2 (blocker) prints the doctor's step-by-step report
to stderr and exits 2 without starting. Nothing is auto-fixed. Exit 1 (problems) logs a
warning and starts.

Data-root lock: taken by the app lifespan; a refused lock (live or stale) is never
stolen, and the launcher exits 3 printing the lock hint.

Web: when `web/dist/index.html` exists, `mount_web` mounts it at `/` after the API routes
(so `/api/*` wins). Without it the API is served alone with a warning. The mount lives in
`sadi.launcher`, not in `app.py`.

Port: the default 8000 is tried first and an ephemeral free port is used when it is busy;
an explicit `--port` that is busy exits 5. The URL is printed (`sadi: serving at ...`).

Binding: only loopback hosts (`127.0.0.1`, `::1`, `localhost`) are accepted; anything else
exits 64 unless `--allow-non-loopback` is given.

Data dir: default is the per-OS user data dir (`platformdirs.user_data_dir("sadi")` when
installed, otherwise a built-in XDG / `LOCALAPPDATA` / macOS fallback). It is printed at start.

Browser: unless `--no-browser`, a daemon thread opens the default browser once the port
accepts connections; failure to open is logged and never stops the server.

Ctrl+C: uvicorn shuts down gracefully (lifespan teardown flushes the WAL and releases the
data-root lock); the launcher then exits 0.

`--selftest`: runs the simulator acquisition (`sadi.doctor.devprobe.probe_sim`) and exits
0 on success, 4 on failure, without starting a server.

Simulator: `--sim` (or `SADI_SIM=1|true|yes` in the environment, read once by the launcher via
`sim_requested`) opens a simulator `DeviceService` (`open_sim_device`) and passes it as
`AppSettings.device`, so `/api/device/status` reports `simulated`. If `sadi_py` is missing or the
open fails the launcher prints the reason and exits 6; the device is closed on shutdown.
The app never reads the environment itself. `python -m sadi` runs the same launcher.
