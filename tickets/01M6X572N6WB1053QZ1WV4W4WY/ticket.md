+++
id = "01M6X572N6WB1053QZ1WV4W4WY"
title = "e2e guided-run: sim LVDT voltage ignores typed calibration heights so calibration fit is degenerate (E pending, CSV export 422)"
type = "bug"
category = "in-progress"
priority = "high"
points = 5
reporter = "lognd"
created = "2026-11-08T08:43:19Z"
updated = "2026-11-08T09:13:05Z"
scope = ["crates/sadi-py/src/**", "python/sadi/launcher.py", "python/sadi/core/device.py", "python/sadi/server/routes/acquisition.py", "web/e2e/**", "python/sadi/core/phases.py"]
+++

found while working ~PX2DPMQ. Under sadi --sim the load program is time-based (clean.json steps at 10 s/310 s) and SimControl (add_weight/remove_weight) is not reachable from Python after open_sim, so all calibration points get identical volts: 'calibration voltages are all equal' (DegenerateX), strain/E omitted, GET /api/export/lctt-csv returns 422 TOO_FEW_POINTS. guided-run.spec.ts fails at the E assertion (results region shows only stress) and would fail at the CSV download. Fix: expose SimControl via the device service and have load-change (or typed mass/height) step the sim so successive points have distinct volts.
