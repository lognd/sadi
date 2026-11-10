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

Order of use: (1) the height inventory, (2) the LVDT calibration (typed slope/offset or points), (3) the
weight inventory. When both a height inventory and weights are given, `POST /plan` returns the weight plan
(`hangs`, the GP-ordered recommendation) plus `heights_plan` (the height table); a typed slope then carries
the height plan's design slope/offset uncertainty (`se_slope_v_per_m`, `se_offset_v`) into the weight plan.
With heights only, the reply is the height plan alone. The CLI does the same with `--heights` and
`--weights` together (heights printed first, then the recommended weights).

Form: a weight inventory table (mass and its own uncertainty per row, same as the height table; duplicates allowed, max 12; CLI `--weights kg:u,...`), a default mass uncertainty for blank rows, wire diameter and its uncertainty,
L0 and its uncertainty, an editable table of LVDT calibration points (height mm / volts, with Add row),
saturation limit, and already captured points as `grams:volts`. The page joins the table into
`cal_points` (`h:v,h:v`) for `POST /plan`. Output: the ordered hang table (weights, total g, tension N, predicted V,
+/- V, reason) and the phase and dropped counts.

Units: the page takes mass in grams and height in millimetres (wire diameter, L0 and the LVDT slope stay in m and
V per m, matching the LabVIEW calibration). It converts to SI (kg, m) before `POST /plan`, so the server and the
CLI remain SI; hang totals and heights are shown back in g and mm.

Regenerating: the planner is stateless, so press Plan again any time. Loads that would saturate are predicted and
dropped before selection; if a real reading saturates anyway, lower the saturation limit, add the points you have
hung to "Already captured" (grams:volts) and plan again to replan the remaining hangs.

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
intercept se reflect it; otherwise it is unweighted OLS.

An explicit slope override (GUI "LVDT slope" and "LVDT offset" fields, CLI `--cal-slope` / `--cal-offset`) skips the fit,
is labelled OVERRIDE in the output and carries no calibration uncertainty. Points plus an override is an
error. Diameter and L0 are REQUIRED: a blank field is an error, never a silent default.

## CLI

    python -m sadi.design.cli --weights 1,1,2,5 --length 0.083 --cal-points 0.001:0.1,0.002:0.21,0.003:0.29 [--hangs N] [--captured N:V,...]

Prints the same table to stdout; exit code 1 when no plan exists.

## Height planning (which gauge heights to use)

`sadi/design/height_plan.py` (`parse_heights`, `plan_heights`, `HeightPlan`) treats gauge heights like
weights: an inventory of heights (m), each with its own uncertainty `u_h`. Duplicates stay distinct ids
(`h1`, `h2`, ...). Heights whose nominal volts exceed the saturation limit are dropped, then the same GP
selector (`selector.select_next`, candidates with `x` = height, `u_x` = `u_h`) orders the rest. Fewer than 2
distinct usable heights is a `HeightPlanError.TooFew` error. The LVDT slope is optional: without
one the plan ranks heights by spread only (no saturation filtering, no predicted volts) and reports the slope
standard error relative to the slope (`rel_se_slope`, `slope_known` false). A typed slope (GUI "LVDT slope", CLI
`--cal-slope`/`--cal-offset`) adds predicted volts, saturation filtering and absolute errors. A height without an
uncertainty gets the default 0.1 mm (`DEFAULT_U_HEIGHT_M`; GUI "Default height uncertainty, mm", CLI `--u-height`).

Each step reports its height, `u_h`, predicted volts and the running slope and intercept standard error
propagated from the chosen heights (weighted least squares with sigma_v = |slope| u_h; a design estimate,
the real fit of measured points is `cal_fit.py`).

    python -m sadi.design.cli --heights 0.001:1e-5,0.002:1e-5,0.003:2e-5 --cal-slope -100

GUI: the "Gauge height inventory" table (height mm / uncertainty mm); when filled, `POST /plan` carries
`heights` and the reply has `height_steps[]`, `se_slope_v_per_m` and `se_offset_v`.

With heights and weights both entered but no calibration (no points, no typed slope), the reply is the height plan plus
`weights_note`: the weights need the calibration, which comes from hanging the planned heights. It is not an error.

### Stacked heights (h1+h2)

Gauge heights can be stacked, so the height plan considers every combination of up to three
inventory heights (`stack_heights`, `MAX_STACK = 3`), not only single heights. A stack is named
`h1+h2`, its height is the sum, and its uncertainty is the root-sum-square of the members'.
Stacks with equal totals collapse to the one with the lowest ids; with a typed slope, stacks that
would saturate are dropped. At least two distinct inventory heights are still required.
