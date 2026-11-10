# User guide: running a test with the app

Status: current

Parent: [Documentation index](index.md). Procedure source: [domain](domain.md) section 6.
Ticket: ~JS6PJJY.

This guide walks an operator through one test: start the app, check the clamps, calibrate,
tare, load the long (elastic) specimen, load the short (plastic) specimen, review, and export.
It only describes behaviour that exists in the tracked code; each step links to the page that
specifies it.

## 1. Start the app

Run `sadi` (the launcher serves the UI and API and opens the
browser). Useful flags: `--sim` (use the built-in simulator), `--port N`, `--no-browser`,
`--selftest`. The launcher runs the [doctor](doctor.md) preflight first; fix anything it
reports before continuing. See [packaging](packaging.md).

## 2. The two specimens

A test uses two specimens (see [lab module](lctt/lab-module.md)):

| Specimen | Role | Default L0 | Gives |
| --- | --- | --- | --- |
| Long | elastic | 0.5 m (editable) | E and r^2 |
| Short | plastic | 0.08313 m (editable) | yield stress |

Edit L0 for each specimen if yours differs; non-finite or non-positive values are refused.
The step rail follows the order Setup, Calibrate, Tare, Elastic, Plastic, Results, Export.

## 3. Procedure

The steps map to [domain](domain.md) section 6.

1. **Clamp-slip pre-check (Setup).** Before loading for real, load lightly (default 10 % of the
   test load), hold (30 s), unload, and repeat (3 cycles), capturing one point per cycle. Setup
   cannot be completed until one point per cycle is captured, though it may be skipped. If a
   cycle shows slip or the zero does not return, re-tighten the clamps and repeat. See
   [clamp check](lctt/clamp-check.md) and [slip](lctt/slip.md).
2. **Calibrate (LVDT).** Enter the known length for each position and capture a point; take at
   least 3 points across the stroke. The fit gives slope, intercept and r^2. See
   [domain](domain.md) 3.3 and [calibration plot](web/calibration-plot.md).
3. **Enter specimen geometry and weights.** Enter repeated readings of L0, diameter and the
   hanger weight (the app also accepts a typed L0 override). See [loading](lctt/loading.md).
4. **Tare.** With the hanger empty and the specimen still, record the tare blocks. Recording
   again replaces the previous tare. See [domain](domain.md) 3.2.
   The server averages the newest 2500 raw (undecimated) samples for each tare and calibration
   capture and stores their mean, sample sd and n; a capture with fewer than 100 samples is
   refused. Uncertainty is sd/sqrt(n) combined with the instrument accuracy.
5. **Hold and confirm, per weight.** Add the next weight and set the total load. The live trace
   shows whether the strain has settled ([settle detector](lctt/settle.md), [live
   trace](web/live-trace.md)). The guidance panel says `Wait: creeping` while the strain
   drifts and `Press Space to accept` once settled; it also suggests the next weights and
   shows a confidence meter and a stop-early recommendation ([guidance](web/guidance.md),
   [guided run](lctt/guidance.md)). In `confirm` mode nothing is captured until you accept;
   accepting before the detector has settled records the point as forced early with a warning
   ([capture modes](lctt/capture.md)). The guidance only proposes the next phase; you decide.
6. **Do the long specimen, then the short specimen.** Run steps 4 and 5 for the long specimen
   (Elastic) and again for the short specimen (Plastic). Phase point caps are 12 and 15.
7. **Review.** The review screen lists every captured point with its flags. Exclude or include
   points, adjust the averaging window, relabel an input, and undo or redo. Edits are
   compensating records; the captured data is never destroyed. See
   [review screen](web/review-screen.md).
8. **Export.** The results screen shows the final values with the 95 % interval and a
   plain-language confidence sentence, then offers the CSV and figure downloads. See
   [export screen](web/export-screen.md) and [CSV export](lctt/export-csv.md).

## 4. Which settle value feeds the E fit

The E fit uses the long (elastic) specimen's points in the chosen window (at least 3 points,
inclusive indices; default is all active points). For each fitted point the app records where
its value came from: `settled_window` (the detector settled), `forced_early` (you accepted
before it settled) or `fixed_dwell` ([modulus](lctt/modulus.md)). The results panel and the
export screen state which settle value fed E, and the CSV carries a `settle_source` column.

To override what feeds E, in the review screen:

- exclude a point you do not trust (for example a forced-early or slip-affected point);
- set the averaging window of a point (`set_window`), or relabel an input (`override_input`);
- choose the E fit window; the suggested window is a hint only and never changes your choice.

Results recompute from the raw data after every edit ([live results](lctt/live-results.md)).

## 5. Creep and slip

In the plastic range strain keeps rising slowly at constant load (creep, roughly linear in log
time; see [creep](lctt/creep.md) and [creep plot](web/creep-plot.md)). Slip in the clamps shows
as a strain jump with no load change. The software flags these and leaves the decision to you
([domain](domain.md) section 7): wait longer, exclude the point, or repeat the step.

## 6. Interpreting results

Each value is shown as best value +/- U with its 95 % interval. A low r^2 for E, saturation
and a missing yield crossing appear as notes ([results panel](web/results-panel.md)). Yield is
found by the 0.2 % offset method ([domain](domain.md) section 5).
