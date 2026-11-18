# Live view UX: readouts, trace, indicators, stress-strain, guidance

Status: draft

Owner ticket: F0B ~KR3SSE1 (design document, no screen code). Builds on, and
never contradicts, [ux.md](ux.md) (layout, keys, status model, sections 4, 5,
8, 9),
[concurrency.md](concurrency.md) (durable gate, display coalescing, stale
markers, section 9), [lctt/settle.md](lctt/settle.md),
[lctt/slip.md](lctt/slip.md), [lctt/creep.md](lctt/creep.md),
[lctt/calibration.md](lctt/calibration.md),
[uncertainty/budget.md](uncertainty/budget.md) and
[core/lab-modules.md](core/lab-modules.md).

Consumers: plot renderer ~MQYWW87 (annotation content, section 7), guidance
UI ~9EFDXQE (section 9), run screens ~74FQXWT, live trace ~7KWS2S7,
stress-strain plot ~3MJNBZY, results ~9PMPWH8. A deviation is a change to this
file in the same ticket.

Scope: the live work area of the Calibrate, Tare, Elastic and Plastic steps
(ux.md 3.2 to 3.5). The wizard shell, step rail and next-action panel frame are
owned by ux.md and are not redesigned here; this file fills the work area and
the panel's guidance and confidence slots.

## 1. Principles specific to the live view

1. Numbers first, always with uncertainty and unit. A bare number is a bug.
2. Nothing blocks. No modal, no sound, no focus steal, no disabled capture
   because of a suggestion. Only a saturated reading refuses a plain accept,
   and `Shift+Space` still records it flagged (ux.md section 4).
3. The software suggests, the human decides (data-safety.md). Every indicator
   below is a suggestion with a reason attached.
4. Only durable data is shown as data (concurrency.md 3.4). Display lag of one
   group commit is expected and invisible at the update rates in section 4.
5. A number never lies about its age: stale, refining and final are visibly
   different (section 8).
6. State is word plus glyph plus shape plus (secondary) colour (section 6).

## 2. Live screen layout (Elastic step, the reference layout)

The work area is the left 60 percent or more of ux.md section 2; the right
column is the next-action panel. Calibrate, Tare and Plastic reuse this layout
with the differences in section 2.2.

```
+-----------------------------------------------+--------------------------+
| ELASTIC  load step 3 of 6   Load: W1+W2 (2.94 N)| NEXT ACTION            |
+-----------------------------------------------+ Add load gently.    |
| V      0.4123 V  +/- 0.0003   [2]  |           | Press Space when Settled.|
| Height 12.034 mm +/- 0.011         |  READOUTS |                          |
| Load   2.94 N    +/- 0.02          |  (5 tiles)| [ Accept (Space) ]       |
| Strain 1.52e-4   +/- 0.04e-4       |           | [ Nudge window ([ / ]) ] |
| Stress 2.31 MPa  +/- 0.06          |           |                          |
+------------------------------------+-----------+ ------------------------ |
| TRACE   V (V) vs t (s)   last 60 s   [Pause view] | GUIDANCE (section 9)   |
|  V ^                  .-'''''---------           | Next: add next load      |
|    |        ___..--'''  [S] settled from 41.2 s  | Why this? [Why?]         |
|    |   __.-'                                     |                          |
|    | .'      |<- load change (marker)            | Alt: smaller step       |
|    +----+----+----+----+---> t (s)               +--------------------------+
|        -60  -45  -30  -15  0                     | CONFIDENCE               |
+---------------------------------+---------------+ Building [####------] 40%|
| SETTLE / CREEP     | SATURATION | STRESS-STRAIN | E ~ 112 GPa +/- 9 (95%)  |
| [~] Creeping       | [OK] 38%   |  sigma ^   o  | Not yet within target.   |
|  0.2 mV/s +/- 0.05 | of range   |    |    o     | [ Why? ]                 |
|  need <= 0.05 for  | |====-----|  |    | o  fit  | ------------------------ |
|  5 s  (2 s so far) | 90% line ^ |    +----> eps | UNCERTAINTY BUDGET       |
|  [=====-----]      |            | E 112 +/- 9   |  1 Load cell  62 % ####  |
|  slip: none        |            |  GPa (95%)    |  2 L0         21 % ##    |
|                    |            |               |  3 Diameter   12 % #     |
+---------------------------------+---------------+--------------------------+
| STATUS BAR (ux.md 5): [Connected] [Creeping] [Signal OK]  Saved 12:04:11   |
+----------------------------------------------------------------------------+
```

Regions, top to bottom in the work area, are in tab order after the rail:

| # | Region | Content | Section |
|---|---|---|---|
| 1 | Readout tiles | V, height, load, strain, stress with uncertainty | 3 |
| 2 | Trace | scrolling V versus time, markers | 4 |
| 3 | Settle/creep panel | state, drift rate, progress to settled, slip | 5.1 |
| 4 | Saturation light | level bar versus range, 90 percent line | 5.2 |
| 5 | Stress-strain | captured points, live point, fit, E text | 7.2 |

In the panel column: next-step (guidance) panel, confidence meter, then the
uncertainty-budget panel (collapsed to the top three inputs, expandable).

### 2.1 Narrow and zoomed layouts

At widths under 1100 px or 200 percent zoom (ux.md section 9) the three bottom
cells stack vertically and the panel column moves below the work area, in the
same reading order. Readouts never drop below five tiles; the trace keeps at
least 160 px of height.

### 2.2 Per-step differences

| Step | Readout tiles | Plot | Notes |
|---|---|---|---|
| Calibrate | V, height (gauge value, typed), no stress/strain | V versus L with fit line | Settle and saturation as above; slope text instead of E |
| Tare | V only (live and averaged) | trace only | A progress bar for the averaging window replaces settle progress |
| Elastic | all five | stress-strain, E fit | reference layout |
| Plastic | all five | stress-strain, E line and 0.2 percent offset line, yield marker | saturation light promoted to the status bar's loudest slot |

## 3. Big readouts with uncertainty

Five tiles in this order: V, Height, Load, Strain, Stress. Each tile:

```
+------------------------------+
| V                      [2]   |   label, source marker (section 8.1)
| 0.4123 V                     |   value, large (>= 28 px), tabular figures
| +/- 0.0003 V   (95%)         |   expanded uncertainty, smaller (>= 16 px)
| [live]                       |   freshness word (section 8)
+------------------------------+
```

Rules:

- Format follows core/formatting.md: value rounded to the uncertainty's leading
  one or two significant digits, uncertainty with the same decimals, SI unit
  shown, never scientific notation unless the exponent is beyond +-3 (strain
  uses `e-4` shown as `1.52e-4`).
- The coverage factor (95%) is stated on every uncertainty, as a short suffix.
- V is the settled-window mean while Settled and the instantaneous 1 s mean
  while Creeping, labelled `(mean 1 s)` or `(settled mean)` so the reader knows
  which. Height, load, strain and stress are derived from V by the lab's
  `recompute` and carry the combined uncertainty; during creep they are shown
  with a creep inflation so the interval visibly widens.
- Load comes from the entered load (typed uncertainty, not a device reading)
  and changes only on a load-change marker.
- Before the first full window after a load change, derived tiles show
  `-- pending` with the same size and position (no layout shift), never zero.
- Each tile is selectable (Tab) and expands to the formula view (section 8.4).
- Assistive tech: tile values update at most once per second (ux.md section 9);
  the polite live region speaks only the settle state change and the new
  settled value, not every tick.

## 4. Trace rendering for quick real-time draw

The trace shows V (the LVDT channel) against seconds, newest at the right.

```
V (V) ^
 0.45 |                          .---------   <- live head, bright dot
      |                    ..--''
 0.40 |   ____...---'''''''    |
      |  /                     +- [S] settled marker (vertical tick + label)
 0.35 | /   <- load change marker [L] (dashed vertical line, label "+load")
      +------+------+------+------+----> t (s)
           -60    -40    -20     0
```

### 4.1 Data path and rates

| Stage | Rate | Rule |
|---|---|---|
| Device to pipeline | sample rate (device config) | never dropped; WAL path (concurrency.md 3.1) |
| Pipeline to display queue | one `TraceFrame` per durable group | coalesced when the queue is full (concurrency.md 3.4), loses nothing on disk |
| Server to browser | at most 30 frames/s | binary WebSocket (~7KWS2S7); frames merge when the client lags |
| Canvas redraw | requestAnimationFrame, capped at 30 fps | skipped when the tab is hidden |
| Readout tiles | 4 Hz visual, 1 Hz assistive | from the newest result envelope |
| Settle/creep, slip | on every block, drawn at 4 Hz | from `StreamStatus` |
| Guidance, confidence | on each result envelope | not time-driven (section 9) |

### 4.2 Decimation

- Window: last 60 s by default, selectable 10 s, 60 s, 5 min (segmented button, or the `W` key).
- Min-max decimation per horizontal pixel column: each column draws the min
  and max of the samples that fall in it, so spikes, slips and saturation hits
  are never averaged away. Cap at 2 x plot width in points.
- The decimator works on the server side from the durable ring and again in
  the client on the received frame; both keep the first and last sample of
  every column so lines join exactly.
- A drawn point is a displayed sample, never a fabricated one: no smoothing,
  no interpolation across gaps. A gap (disconnect, stall) is drawn as a break
  with a hatched band and the word `gap`.
- Canvas only (no per-point DOM). One path per series, one clear per frame.
  The previous frame's decimated buffer is reused when the window has not
  moved. Budget: 4 ms per frame on the reference laptop.
- The y axis autoscales slowly (ease over 2 s, never shrinks while a slip or
  load change is in the window) so the trace does not jitter.

### 4.3 Trace content and what is shown when

| Condition | Shown |
|---|---|
| Loading (no full window since load change) | trace, load-change marker `[L]`, tile values `-- pending` |
| Creeping | trace plus a thin dashed fitted drift line over the last window and its slope text; derived tiles with inflated uncertainty |
| Settled | trace plus a shaded band over the settle window and a `[S]` marker at `settled_index`; derived tiles with settled uncertainty |
| Slip suspected | a `[!]` marker at the step, text "possible clamp slip, size X mm" (lctt/slip.md); capture not blocked |
| Saturated | the clipped samples drawn as hollow squares on the limit line, band hatched |
| Paused view | the trace freezes, label `view paused`; data still acquired and saved; `Resume` returns to live |

Markers are distinct by shape and letter, not colour (section 6).

## 5. Indicators

All three indicators in this section duplicate the status bar's three slots
(ux.md section 5) with more detail; the status bar remains the always-visible
summary and the only thing present on every step.

### 5.1 Settle / creep

Source: `StreamingSettleDetector` (`loading`, `creeping`, `settled`).
Suggestion only; a human accepts.

```
 SETTLE / CREEP
 [~] Creeping            <- word + glyph
 drift 0.20 mV/s +/- 0.05
 need <= 0.05 mV/s for 5 s  (held 2 s)
 [=====-----]            <- progress to the dwell
 slip: none              <- or "[!] possible slip 0.012 mm at 41.2 s"
```

| State | Glyph and word | Shape | Panel text |
|---|---|---|---|
| loading | `[.] Loading` | open circle | "Waiting for a full window (3 of 5 s)." |
| creeping | `[~] Creeping` | wave | drift rate with uncertainty, dwell progress |
| settled | `[=] Settled` | flat bar | "Settled for 6 s. Press Space to accept." |
| slip | `[!] Slip?` | triangle | size and time; advisory only |

When creeping, the panel states the remaining wait as a range ("about 3 to 8
s more, if the drift keeps falling") only when the creep fit (lctt/creep.md)
gives one; otherwise it shows the dwell progress only. When settled, the drift
line collapses to "drift within limit". Settled latches: later blocks do not
un-settle it (lctt/settle.md) but a new load-change marker resets to loading.

### 5.2 Saturation light

```
 SIGNAL
 [OK]   Signal OK      level  38% of range  |====---------|
 [~]    Near limit     level  91% of range  |==========-- |  (90% line ^)
 [X]    SATURATED      level 100%           |=============|  clipped
```

- States and thresholds are ux.md section 5: Near limit at 90 percent of range,
  SATURATED when the input is clipped. The bar shows the instantaneous level
  and the peak over the current point (a thin tick), so a brief clip is not
  forgotten after the level drops.
- The glyph and word change with state; the bar adds a third cue (length).
- On SATURATED: Space accept is refused with the ux.md section 6 message ("The
  reading is at its limit (saturated). Lower the load, then
  try again."), shown inline at the light, not as a modal. `Shift+Space` records
  it flagged `saturated`. Nothing else is blocked.
- Saturated samples are marked on the trace (section 4.3) and excluded from the
  fit by default; the points table shows `sat`.

### 5.3 Combined accept readiness

The Accept button label reflects what a press would do, so the user sees the
consequence before pressing:

| State | Button | Space |
|---|---|---|
| Settled, OK | `Accept (Space)` | accepts |
| Creeping | `Accept unsettled (Shift+Space)` | refuses with reason; Shift+Space accepts flagged |
| Saturated | `Accept flagged (Shift+Space)` | refuses with reason |
| Slip suspected | `Accept (Space)` with a `[!]` badge | accepts; flag `slip_suspected` stored |

Never disabled, never hidden (principle 2).

## 6. Colour, shape and screenshot-safe coding

Rules, binding on all live-view widgets and the plot renderer:

1. Every state carries a word and a glyph (ux.md section 9). Colour is a third,
   redundant cue, so a greyscale screenshot or print stays readable.
2. Palette is colour-blind safe (Okabe-Ito based) and checked for deuteranopia,
   protanopia and tritanopia:

| Role | Colour (hex) | Pair with |
|---|---|---|
| Data, trace | blue `#0072B2` | solid line |
| Fit, model | vermillion `#D55E00` | dashed line |
| Confidence band | sky `#56B4E9` at 25% alpha | hatch-free fill |
| Captured point | black `#000000` | filled circle |
| Rejected or flagged point | grey `#666666` | hollow circle with cross |
| Live (uncommitted) point | orange `#E69F00` | ring with centre dot |
| OK | bluish green `#009E73` | `[OK]`, filled circle |
| Warning | yellow `#F0E442` on a dark outline | `[~]`, triangle |
| Error, saturated | vermillion `#D55E00` | `[X]`, square |

3. Marker shapes are unique per meaning: captured = filled circle, live =
   ringed dot, rejected = hollow circle with cross, load change = dashed
   vertical line, settled = solid tick, slip = triangle, yield = diamond,
   gap = hatched band.
4. Line styles differ as well: data solid, fit dashed, offset line dash-dot,
   CI band as a filled region with a thin outline (so it survives a one-bit
   print).
5. Contrast is at least 4.5:1 for text and 3:1 for graphical parts on the light
   theme; the yellow warning uses a dark outline to meet it.
6. Screenshot and export safety: legends and annotations (section 7) are drawn
   into the canvas, not as HTML overlays, so a PNG or SVG export contains
   them. The pause, stale and simulated banners are drawn into the export as
   well (section 8.5). No state exists only in a hover or tooltip.
7. No flashing or blinking; a state change is a single static change. Motion is
   limited to the trace scroll and progress bars (ux.md section 9).

## 7. Plots: annotation content (consumed by F3 to F7)

Every plot has: a title, axis labels with units, a legend with line and marker
samples, a subtitle with run name, specimen, date and `data_version`, and a
footer with the coverage statement ("Bands and +/- are 95 % intervals").
Text is ASCII in this document; the renderer may typeset Unicode math, the
strings below are the canonical content.

### 7.1 Live trace

| Item | Content |
|---|---|
| Title | `LVDT voltage, load step 3 of 6` |
| X axis | `Time since window start (s)` (ticks negative to 0, newest at 0) |
| Y axis | `LVDT voltage (V)` |
| Legend | `V (measured)`, `Drift fit (last window)`, `Settled window`, `Load change`, `Possible slip`, `Saturated` |
| Annotations | `[L] +load (0.98 N)` at load changes, `[S] settled 41.2 s`, drift text `drift 0.20 +/- 0.05 mV/s` |
| Bands | none on the live trace (a band would imply a model) |

### 7.2 Live stress-strain with E fit

```
 Stress-strain, elastic fit
 sigma (MPa) ^                          o live (ringed)
        20   |                   o  o
        15   |             o  o      / fit, 95% band
        10   |        o  o     ,-'' 
         5   |   o  o   .-''
         0   +--+---+---+---+---+---> strain (1e-4)
             0   2   4   6   8  10
 --- E = 112.4 +/- 4.1 GPa (95%)   fit: sigma = E*eps + b   n = 6   r^2 = 0.9994
 o captured   (o) live   x rejected   --- fit   [###] 95% band of the fit line
```

| Item | Content |
|---|---|
| Title | `Stress-strain, elastic fit` (Plastic: `Stress-strain with 0.2 % offset yield`) |
| X axis | `Strain (1e-4)` or `Strain (microstrain)`; unit stated, dimensionless |
| Y axis | `Stress (MPa)` |
| Points | captured (filled), live (ringed, hollow until accepted), rejected (cross) |
| Error bars | 95 % in both axes where they exceed marker size; caps shown |
| Fit line | dashed vermillion over the selected window only; faint extension outside it |
| CI band | 95 % confidence band of the fit line, shaded, thin outline |
| Equation text | `sigma = E * eps + b`, `E = 112.4 +/- 4.1 GPa (95 %)`, `b = 0.12 +/- 0.05 MPa`, `n = 6`, `r^2 = 0.9994`, `window: points 2..6` |
| Plastic extras | offset line `0.2 % offset` dash-dot; yield diamond with `sigma_y = 212 +/- 9 MPa (95 %)` |
| Legend | `Captured`, `Live (not accepted)`, `Rejected`, `Fit (E)`, `95 % band`, `0.2 % offset`, `Yield` |

The fit window is selectable: `[` and `]` and `Shift+[` / `Shift+]` nudge
start and end (ux.md section 4); the fit text and band update on the next
envelope and show the stale marker until then (section 8). The live point
follows the current V; it joins the fit only after accept.

### 7.3 Calibration plot

| Item | Content |
|---|---|
| Title | `LVDT calibration, height versus voltage` |
| X / Y | `Voltage (V)` / `Height (mm)` (the fit is height = slope * V + intercept, lctt/calibration.md) |
| Text | `L = (a +/- ua) mm/V * V + (b +/- ub) mm`, `r^2`, `n`, residual summary |
| Band | 95 % band of the line; residual strip beneath with `Residual (mm)` |

### 7.4 Creep / settle detail (opened from the settle panel)

| Item | Content |
|---|---|
| Title | `Creep after load change` |
| X / Y | `ln(time since load) (ln s)`, `Strain (1e-4)` or `V (V)` |
| Text | `strain = a + b ln(t - t_load)`, `b = ... +/- ... ` (lctt/creep.md) |
| Band | 95 % band of the fit |

### 7.5 Residuals and budget plots

Residual plot: `Residual (units)` versus the fitted variable, zero line,
2-sigma band, lack-of-fit flag text when the lack-of-fit guard trips.
Budget chart: horizontal bars, label `Contribution to variance (%)`, rows named
as in uncertainty/budget.md, dominant row outlined.

## 8. Stale numbers, refinement progress, budget, formulas

### 8.1 Stale-number marker and freshness words

Driven by the result envelope `state` and `data_version` (concurrency.md 9.2).
Every derived number (E, readout tiles derived from the fit, confidence, budget)
shows one freshness word and glyph, in a fixed slot at the tile's top right:

| Envelope state | Word | Glyph and look | Meaning |
|---|---|---|---|
| (instrument value) | `live` | `[*]` | straight from the stream, not a model result |
| `stale` | `stale` | `[?]`, value in grey italic | a point was accepted; recompute pending |
| `analytic` | `quick` | `[~]` | fast estimate, MC refinement pending |
| `refining` | `refining 62%` | `[~]` plus mini bar | refinement in progress |
| `final` | `final` | `[=]` | all work for this `data_version` is done |

```
 E   112.4 GPa +/- 4.1  [?] stale          <- instant after Accept, grey italic
 E   112.6 GPa +/- 4.3  [~] quick          <- tens of ms later
 E   112.5 GPa +/- 4.0  [~] refining 62%   <- MC running
 E   112.5 GPa +/- 4.0  [=] final
```

Rules: the sequence is exactly the one in concurrency.md 9.3 (stale, analytic,
refining, final). A stale value is dimmed, never hidden, and the tile keeps its
size. The stale marker is in exported plots and screenshots (section 8.5). The
client drops out-of-order envelopes with the rule in concurrency.md 9.2, so a
marker never moves backwards. A number older than 5 s with no new envelope and
a connected pipeline shows `[?] stale (no update 5 s)`.

### 8.2 MC refinement progress

A thin indicator under the confidence meter and in the status bar tail:

```
 REFINING   E (Monte Carlo)   [######----] 62%    [ Details ]
```

- Fed by `Progress.fraction` of the job (concurrency.md section 8). Determinate
  bar; if no fraction is available a labelled indeterminate bar with elapsed
  time, never a spinner alone.
- One row per running job (E, yield). Rows disappear on `final`.
- A superseded job's row is replaced, not stacked (latest wins, 7.1). A new
  accepted point resets the bar to 0 with the stale marker on its numbers.
- Never blocks: accept, undo and nav work during refinement. `Esc` does not
  cancel a refinement; `[ Details ]` offers `Cancel refinement` (the quick
  estimate stays, marked `quick`).

### 8.3 Uncertainty-budget panel (dominant input)

Placed in the panel column under the confidence meter, collapsed to the top
three rows by default, expandable in place. Fed by `Budget.payload()`
(uncertainty/budget.md) for the headline result of the step (E in Elastic,
slope in Calibrate, yield in Plastic).

```
 UNCERTAINTY BUDGET  for E            [ Show all ] [ Formula ]
 Dominant input: Load cell mass (62 % of variance)
  1 Load cell mass   0.98 N +/- 0.02   62 %  ############
  2 Length L0        83.13 mm +/- 0.05  21 %  ####
  3 Diameter d       0.50 mm +/- 0.01   12 %  ##
  total u(E) = 4.1 GPa (95 %)
 Tip: a better load measurement would help most.
```

Rules: rows ranked by `rank`; percent from `percent` (may be negative with
negative correlation, then shown with a minus and a footnote); the dominant row
is outlined and named in a sentence (a screen-reader line). The "Tip" is a
plain-language hint generated only from the dominant row, advisory, and hidden
if the dominant input is not something the user can change (for example a
fitted slope). The panel carries the same freshness word as its result.

### 8.4 Formula and derivation view

Opened by `[ Formula ]`, the `E` key, or Enter on a focused readout tile. Placement: a non-modal drawer sliding over the lower half of the
work area (not over the panel), so readouts and the Accept button stay visible.
`Esc` closes it; focus returns to the opener.

```
+-----------------------------------------------------------------+
| FORMULA   Young's modulus E                          [ Close Esc ]|
| E = (F / A) / (dL / L0)                                         |
| F = 2.94 N   A = pi d^2 / 4 = 1.96e-7 m^2   dL = 12.0 um        |
| substituted: E = (2.94 / 1.96e-7) / (1.52e-4) = 98.7 GPa  ...   |
| u(E)^2 = sum (dE/dx_i)^2 u_i^2 + covariance terms               |
|   dE/dF u(F) = ...   dE/dL0 u(L0) = ...        see budget       |
| Source: domain.md section 3; code: sadi.labs.lctt               |
+-----------------------------------------------------------------+
```

Content comes from the lab (`LabModule` analysis metadata, core/lab-modules.md):
symbolic form, substituted numbers with units, sensitivity coefficients and the
link to the budget row. Read-only; never editable. Each tile and each result
has exactly one formula entry, so the view is discoverable and uniform.

### 8.5 Export and screenshot state

Anything stale, simulated or paused at export time is stamped into the image
(`STALE`, `SIMULATED DATA`, `view paused`) in the footer, with `data_version`,
so a figure can always be traced to a durable prefix.

### 8.6 Behaviour on disconnect

| Event | Display | Data |
|---|---|---|
| Device drop | Source slot `Disconnected`; trace freezes at the last sample with a hatched `gap` growing to the right; tiles keep the last value, marked `[?] stale (device lost)`; reconnect prompt in the panel | all durable data intact; accept refused with "No live reading. Reconnect the device, then try again." (inline) |
| Device returns | gap closed with a break (no interpolation); settle state resets to `loading`; a marker `[R] reconnected` on the trace | acquisition resumes; unsettled point stays flagged |
| Server socket drop | banner "Connection to the app lost. Retrying." ; everything marked `stale`; no data lost, it is in the WAL | client reconnects, gets the latest envelope per key (concurrency.md 12) |
| Store stall | `NOT SAVED` in the save indicator, error style (ux.md section 6) | acquisition stopped by the pipeline (concurrency.md 3.5); shown points are only those already durable |

Previously accepted points, the fit and E remain visible and editable in all
cases (stale-marked if the process restarted until recomputed).

## 9. Guidance placement (suggest only)

Guidance occupies two fixed slots in the panel column of every live step,
below the primary button, as ux.md section 8 binds. Content comes from the confidence indicator payload.

### 9.1 Confidence meter and stop indicator

```
 CONFIDENCE
 Building [####------] 40%         <- state: building | enough | high
 E ~ 112 GPa +/- 9 (95%)  target +/- 5
 [ Why? ]
 - - - - - - - - - - - - - - - - - -
 (hidden until enough)
 Suggestion: you can stop loading here.   [ Keep going ] [ Finish phase ]
```

- Mapping from the payload: `collecting` is `building`, `enough` is `enough`,
  the `high` word is shown when `ratio <= 0.5`; `diminishing` shows
  "More points will not help much." with `building` kept as the state;
  `unreliable` shows `[i] limited` and never a stop suggestion.
- The percent is `min(1, 1 / ratio)` rounded to 10, labelled "rough guide" in
  [Why?]. Words first, meter second (ux.md section 8).
- The stop line is quiet: no modal, no sound, no focus change, no auto-advance,
  and capture, undo and navigation continue unchanged. `Keep going` hides it for
  the phase until the estimate changes materially; `Finish phase` (also `F`)
  asks the standard confirmation.
- Screen readers: `aria-live="polite"`, announced at most once per state
  change.
- The target half-width H* is shown and editable inline (`target +/- 5`, click
  or Tab+Enter); changing it re-runs the suggestion as a new job.

### 9.2 Where it never appears

Not in the status bar (reserved for the three ux.md indicators), not over the
trace or plots, never as a toast. The only interruptions allowed are the
data-loss modals of ux.md section 6.

## 10. Nothing blocking: summary of what stays live

| Situation | Still works |
|---|---|
| Creeping | trace, readouts, Shift+Space accept flagged, undo, nav, nudge |
| Saturated | everything except plain Space; Shift+Space flagged |
| Refining | all input; numbers marked until final |
| Guidance computing | accept, edits; old suggestion dimmed |
| Stop suggested | continue loading; capture unchanged |
| Disconnected | review, edit, undo, navigate saved points |
| Stalled store | review only; ux.md section 6 message |

## 11. Undo, redo and re-editable points

Points table (work area, beside or below the stress-strain plot, per step):

```
 #  Load N  Stress MPa  Strain      Status      Flags
 1  0.98    1.31 +/-.04 0.65e-4     accepted
 2  1.96    2.31 +/-.06 1.20e-4     accepted
 3  2.94    (live)      (live)      creeping    -
 4  2.94    3.40 +/-.06 1.52e-4     rejected    unsettled
```

- Undo (`Z` or Ctrl+Z) and redo (`Shift+Z` or Ctrl+Y) cover accept, remove,
  flag change, window nudge and point re-edit (ux.md section 4); unlimited
  within the session; raw samples are never deleted, undo only changes which
  are used.
- Every point row is selectable (arrow keys when the table has focus) and
  re-editable: change `include / exclude`, edit the settle window for that point
  (`[`, `]`, `Shift+[`, `Shift+]`), re-accept from a different window. Edits are
  durable EDIT records (concurrency.md 9.1); each bumps `data_version`, so the
  fit, E, confidence and guidance go through stale, quick, refining, final.
- An edit to a point of an earlier step marks later steps `[!]` in the rail
  (ux.md section 2.1) instead of recomputing them silently.
- Undo toasts are not used; the table row and a one-line status ("Undid:
  accepted point 4") in the panel's secondary area announce it politely.
- A removed point stays visible as a grey rejected row with the reason and a
  `Restore` action; it is greyed on the plot with a cross marker.

## 12. Keyboard map for the live view

Extends ux.md section 4; the global map is unchanged. Keys are active only when
no text field has focus.

| Key | Action |
|---|---|
| Space | Accept the live point (refuses with reason while Creeping or Saturated) |
| Shift+Space | Accept anyway, flagged `unsettled` / `saturated` |
| Z / Ctrl+Z | Undo |
| Shift+Z / Ctrl+Y | Redo |
| [ and ] | Window start earlier / later |
| Shift+[ and Shift+] | Window end earlier / later |
| Up / Down | Select previous / next point row (table focus) |
| Delete or X | Exclude the selected point (undoable) |
| R | Restore the selected excluded point |
| P | Pause or resume the trace view (data keeps recording) |
| W | Cycle trace window 10 s, 60 s, 5 min |
| G | Focus the guidance slot (read the suggestion; no action) |
| B | Toggle the uncertainty-budget panel (collapsed or all rows) |
| E | Open the formula view for the focused tile or headline result |
| F | Finish the phase (confirmation) |
| Esc | Close the formula drawer or dialog; cancel averaging |
| ? | Show the map |

Every shortcut also has a visible button (ux.md section 9). `E`, `B`, `G`, `P`,
`W`, `R`, `X` do not conflict with ux.md (which binds Space, Enter, Z, F, Esc,
?, brackets, arrows, Tab). Letters are lower and upper case equivalent.

## 13. Logging

Front-end diagnostics go to the server log through the app log channel (never
console printing): INFO on state changes (settle state, saturation state,
accept, undo, redo, edit, window change, pause), WARNING on refused accepts,
disconnects, out-of-order envelopes and stale timeouts, ERROR on render
failures. Each record carries `data_version`, the point number and the cause.

## 14. Acceptance map for the tickets

| Criterion | Where |
|---|---|
| 1 Layout: readouts, trace, settle/creep, saturation, stress-strain with E fit, next-step panel, confidence meter | sections 2, 3, 4, 5, 7.2, 9 |
| 2 Rates, decimation, creeping versus settled, colour/shape coding, disconnect | sections 4.1, 4.2, 4.3, 6, 8.6 |
| 3 Plot annotation content for F3 to F7 | section 7 |
| 4 Stale marker, MC progress, budget panel, formula view placement | sections 8.1, 8.2, 8.3, 8.4 |

## 15. Open questions

- The creep wait estimate (5.1) depends on whether the creep fit is cheap
  enough to run per block; if not, the panel shows dwell progress only.
- Whether the `high` confidence word (`ratio <= 0.5`) matches the PH1
  ~G2YNMJB thresholds; wording and placement do not depend on it.
- Keys `E`, `B`, `G`, `P`, `W`, `X`, `R` should be confirmed in the F14
  usability pass for accidental presses; none is destructive without undo.

## Idle pause, resume and firmware (audit4 L1/L2/L6)

- The capture-refused hint for an idle pause reads "press Resume live readings to start again"; Mark load change is not needed.
- Resume after idle (and `start_streaming` on an unopened service) returns `LiveError.NoDevice` / a `NOT_FOUND` device error when the board is detached or errored, never a 500.
- The SETTINGS `device.firmware` row records the literal `unknown` until the handshake version is plumbed through.
