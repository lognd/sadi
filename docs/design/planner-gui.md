# Planner GUI and CLI

Status: current

Owner: ~RH6VBAE.

Standalone, advisory weight planner for use beside the regular LabVIEW VI. No sadi session is needed and
nothing is written to disk. Both front ends call `sadi.design.plan.plan` (see `weight-plan.md`) and share
the parsing and request building in `sadi/design/cli.py` (`parse_weights`, `parse_captured`,
`build_request`; all return typani `Result`).

## Browser GUI

    python -m sadi.design.gui [--port N] [--no-browser]

Starts a stdlib `http.server` bound to `127.0.0.1` only (a free port unless `--port` is given), prints
the URL and opens it with `webbrowser`. `GET /` serves one self-contained page (inline CSS and JS, no
network assets, no node, no tkinter). `POST /plan` takes the form as JSON and replies
`{"ok": true, phase, counts, hangs[]}` or `{"ok": false, "error": msg}`.

Form: weights in kg (duplicates allowed, max 12), mass uncertainty, wire diameter and its uncertainty,
L0 and its uncertainty, an editable table of LVDT calibration points (height m / volts, with Add row),
saturation limit, and already captured points as `kg:volts`. The page joins the table into
`cal_points` (`h:v,h:v`) for `POST /plan`. Output: the ordered hang table (weights, total kg, tension N, predicted V,
+/- V, reason) and the phase and dropped counts.

## Calibration (derived, not typed)

The planner fits volts = slope*height + intercept by least squares from the entered points, reusing
`sadi.labs.lctt.calibration.fit_calibration` (x = height m, y = volts) via `sadi/design/cal_fit.py`
(`resolve_calibration`, `parse_cal_points`, `Calibration`). The reply and CLI show slope, intercept,
their standard errors, r2 and n. At least 3 points (the lctt fit needs dof >= 1) at 2 or more distinct
heights are required; fewer is a clear error, never a default. The slope se, intercept se and their
covariance propagate into each hang's predicted-volts uncertainty (`+/- V`), added in quadrature to the
mass-uncertainty term.

Each point may carry an optional height uncertainty (`h:v:u_h`, metres). When every point has one the fit
is weighted (effective variance: u_h scaled by the slope, re-weighted until settled) and the slope and
intercept se reflect it; otherwise it is unweighted OLS. (Height selection from an inventory is a
separate follow-up.)

An explicit slope override (GUI "Override (advanced)", CLI `--cal-slope` / `--cal-offset`) skips the fit,
is labelled OVERRIDE in the output and carries no calibration uncertainty. Points plus an override is an
error. Diameter and L0 are REQUIRED: a blank field is an error, never a silent default.

## CLI

    python -m sadi.design.cli --weights 0.1,0.1,0.2,0.5 --length 0.083 --cal-points 0.001:0.1,0.002:0.21,0.003:0.29 [--captured kg:V,...]

Prints the same table to stdout; exit code 1 when no plan exists.
