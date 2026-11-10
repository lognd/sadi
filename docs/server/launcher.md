# Launcher (`sadi`)

Status: current

Console script `sadi` (`sadi.launcher:main`).

- `sadi serve` (also bare `sadi`, or `sadi --port N`): runs the doctor preflight
  read-only, then starts uvicorn on `create_app(AppSettings(data_root=...))`.
  Options: `--host` (loopback only, default `127.0.0.1`), `--port` (default 8000),
  `--data-root` / `--data-dir`, `--web-dist` (`web/dist`), `--skip-preflight`,
  `--no-browser`, `--sim`, `--selftest`, `--version`, `--allow-non-loopback` (UNSAFE), `--recover-stale`.
- `sadi doctor ...`: passthrough to `sadi-doctor`.

Preflight: a doctor exit code of 2 (blocker) prints the doctor's step-by-step report
to stderr and exits 2 without starting. Nothing is auto-fixed. Exit 1 (problems) logs a
warning and starts.

Data-root lock: taken by the app lifespan; a refused lock (live or stale) is never
stolen, and the launcher exits 3 printing the lock hint.

Crash recovery: after a crash or power loss the lock file still names a dead pid. The
refusal says so in plain words and names the exact command, `sadi serve --recover-stale`.
The flag only takes over a lock whose OS lock is free (the holder is gone); a live holder is
still refused. It never deletes or rewrites session data, and without it nothing changes.

Port check: `_port_free` sets `SO_REUSEADDR` (POSIX, like uvicorn) so a port left in
TIME_WAIT by a crashed server is not reported busy and the default port is kept.

Unwritable data root: before anything else the launcher checks (read-only, creating nothing)
that the data folder, or its nearest existing parent, is writable. If not it exits 3 with a
"Permission denied" hint suggesting `--data-root <folder>`.

Web: when `web/dist/index.html` exists, `mount_web` mounts it at `/` after the API routes
(so `/api/*` wins). Without it the API is served alone with a warning that names the fix (`cd python && uv run python ../packaging/build_ui.py`). The checkout fallback is resolved from the package location (`sadi.webdist.CHECKOUT_WEB_DIST`, shared with the WEB-010 doctor probe), never the cwd. The mount lives in
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

AD3: `--ad3` (or `SADI_AD3=1|true|yes`) opens the Digilent AD3 via `open_managed_ad3` and always
closes it on exit, including on errors and SIGTERM; failure exits 7. See
[AD3 wrapper](../bench/ad3.md#launcher-integration).

Simulator: `--sim` (or `SADI_SIM=1|true|yes` in the environment, read once by the launcher via
`sim_requested`) opens a simulator `DeviceService` (`open_sim_device`) and passes it as
`AppSettings.device`, so `/api/device/status` reports `simulated`. If `sadi_py` is missing or the
open fails the launcher prints the reason and exits 6; the device is closed on shutdown.
Verification status: `open_sim_device` was exercised against a real `sadi_py` built with
`maturin develop` (it opened, streamed a 50-sample block, stopped and closed cleanly); the pytest
`test_open_sim_device_real_simulator_streams_samples` re-runs this and is skipped when `sadi_py`
is not importable. The other launcher tests inject a fake device.
Real board: with none of `--sim`, `--synthetic-specimen` or `--ad3`, the launcher opens the SADI
board over serial (`sadi/server/device_open.py::open_real_device`, a `DeviceSource(kind="serial")`)
on `--device-port`, else `SADI_PORT`, else `/dev/ttyUSB0` (auto-detect by FTDI id on Windows) and
passes it as `AppSettings.device`, so `/api/stream` works. If the board cannot be opened the launcher
prints a plain-language WARNING (port, cause, "plug in the SADI board...") and still starts with no
device (exit 0 on shutdown): `/api/device/status` reports `attached=false`, status `error`, no live
acquisition exists so nothing is recorded, and closed sessions can be browsed and exported. No
session is created or changed by this path; restart with the board attached to capture. A bad data
folder or lock still exits. Tests use a fake serial opener; none touch a real port.
The app never reads the environment itself. `python -m sadi` runs the same launcher.

## Live acquisition

When a device is present (`--sim` or real; the real path is UNVERIFIED on hardware) the launcher
builds a `Bus` and a `LiveAcquisition` (`sadi/server/live.py`) and passes both in `AppSettings`,
which mounts `WS /api/stream`. The pipeline is created per open session, writes raw blocks to that
session's WAL (decimated by 25 for analysis) and publishes to the Bus. Device or pipeline failures
are logged and recorded as a fault; they never crash the app.
