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
L0 and its uncertainty, LVDT calibration slope (V/m) and offset (V), saturation limit, and already
captured points as `kg:volts`. Output: the ordered hang table (weights, total kg, tension N, predicted V,
+/- V, reason) and the phase and dropped counts.

The calibration slope, diameter and L0 are REQUIRED: a blank field is an error, never a silent default.
The earlier 40 V/m slope was only a placeholder and is not used anywhere.

## CLI

    python -m sadi.design.cli --weights 0.1,0.1,0.2,0.5 --length 0.083 --cal-slope 12 [--captured kg:V,...]

Prints the same table to stdout; exit code 1 when no plan exists.
