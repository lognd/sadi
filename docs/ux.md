# UX design: wizard flow, step rail, wireframes, keyboard map

Status: current

Owner ticket: F0 ~GKVPN2E (design document, no screen code). Consumers:
F0B ~KR3SSE1 (live view), F8 ~9PMPWH8 (results panel), F9 ~2ZQVKAB (wizard
shell), F10 (setup), F11 ~74FQXWT (run screens), F12
~9EFDXQE (guidance UI), F14 (usability pass, section 10). Implementers follow
this file exactly; a deviation is a change to this file in the same ticket.

Domain terms (tare, LVDT calibration, elastic and plastic runs) are defined in
[domain.md](domain.md); the settle suggestion in [lctt/settle.md](lctt/settle.md);
non-blocking and "latest wins" behaviour in [concurrency.md](concurrency.md);
the human-confirms rule in [data-safety.md](data-safety.md); the module
contract in [core/lab-modules.md](core/lab-modules.md).

## 1. Principles

1. One app, one linear wizard. A persistent step rail shows where you are.
2. One big next-action panel says what to do now, in one sentence, with one
   primary button.
3. The software suggests; the human decides. Nothing advances, captures,
   stops or discards without a user key or click (section 8).
4. In and out in minutes: defaults answer the questions a student should not
   have to (section 7).
5. Minimal modes: only Guided (default) and Expert. Expert only reveals
   controls (manual window, manual tare, free navigation); it never changes
   the data path.
6. Nothing is shown as data until it is durable (concurrency.md, DS I6).
7. Light theme only. Plain language; numbers carry units.

## 2. Layout

```
+--------------------------------------------------------------------------+
| SADI  LCTT   Run: 2026-11-08 A        [Guided|Expert]   [Help ?] [Save *]|
+--------------------------------------------------------------------------+
| (1)Setup > (2)Calibrate > (3)Tare > (4)Elastic > (5)Plastic |
|            > (6)Results > (7)Export                                       |
+-----------------------------------------------+--------------------------+
|                                               |  NEXT ACTION             |
|  WORK AREA                                    |  One sentence.           |
|  (live view, forms, tables: per step)         |  [ Primary button ]      |
|                                               |  secondary link          |
|                                               |  ----------------------  |
|                                               |  CONFIDENCE (section 8)  |
+-----------------------------------------------+--------------------------+
| STATUS BAR: [Connected|Simulated] [Settled|Creeping] [Signal OK|SATURATED]|
|             disk: saved 12:04:11   keys: Space=accept  Z=undo  ?=help    |
+--------------------------------------------------------------------------+
```

- Header: run name, mode toggle, help, save indicator.
- Step rail: always visible, in the same place on every screen.
- Work area: left, at least 60% of the width. Next-action panel: right,
  fixed width, never scrolls away.
- Status bar: always visible, three indicators (section 5).
- Sticky offset: `--top-h` (scroll padding and the sticky live panel's `top`) is
  the measured height of the sticky header stack (`.app-top`: instrument bar,
  debug strip, banners), published by `watchStickyTop` (`web/src/hooks/useStickyOffset.ts`)
  via ResizeObserver, so banners appearing or a short viewport never leave
  sticky content overlapping. `11rem` in `styles.css` is only the fallback.
  The variable is published only while `.app-top` is really `position: sticky`;
  under the narrow-viewport media rule (static header) it is removed so the
  stylesheet's `1rem` applies.
- Session facts: the status bar polls `/api/session` slowly while no session is
  open, so `SessionSetup` (after create/resume) and `CloseSession` call
  `useRefreshFacts()` to poll at once; "No session" never lingers after either.
- Setup list: sessions whose provenance is synthetic carry a bold SYNTHETIC badge.
- Run hints: the first point of a phase needs the mark button; after each Accept
  the next point opens by itself, and the button only restarts the settle timer.

### 2.1 Step rail states

Each step shows one of five states, by glyph and word, never by colour alone:

```
 [x] done        [>] current      [ ] upcoming      [!] needs attention
 [-] skipped (with reason, e.g. "Tare: reused from 11:58")
```

```
 [x]Setup  [x]Calibrate  [>]Tare  [ ]Elastic  [ ]Plastic ...
```

Rules: done steps are clickable (review, redo with confirmation, section 3.1);
upcoming steps are not clickable in Guided mode (the next-action button is the
only way forward) and are clickable in Expert mode. The current step is
bold and boxed. A step turns `[!]` when its data was changed after a later
step consumed it (stale downstream results; shown, never auto-recomputed
silently).

## 3. Flow and wireframes

Every wireframe shows the work area and the next-action panel only; the
header, rail and status bar are as in section 2.

### 3.1 Step 1 Setup

Purpose: name the run, pick device (or simulator), enter the specimen.

```
+-----------------------------------------------+--------------------------+
| SETUP                                         | NEXT ACTION              |
| Device   (o) SADI on COM3   ( ) Simulator     | Check the device is      |
|          status: Connected                    | found, enter the         |
| Specimen name   [ Cu wire A ........ ]        | specimen, then continue. |
| Long length L0  [ 0.08313 ] m   (default)     |                          |
| Wire diameter d [ 0.50    ] mm                | [ Continue  (Enter) ]    |
| Hanger weight   [ 0.98    ] N                 |                          |
| Data folder     ~/sadi-data  [Change]         | Missing: diameter        |
|                                               |                          |
| Advanced (collapsed): sample rate, units      |                          |
+-----------------------------------------------+--------------------------+
```

Defaults skip questions: device auto-selected when exactly one is found, L0
and hanger weight from the last run, data folder from config. Continue stays
disabled until required fields validate; the panel names what is missing.

### 3.2 Step 2 Calibrate (LVDT)

Purpose: capture (voltage, length) points to fit the LVDT calibration.

```
+-----------------------------------------------+--------------------------+
| CALIBRATE                                     | NEXT ACTION              |
| Live V: 1.2345 V   [Settled]                  | Set the gauge block to   |
|  V ^        .                                 | 12.00 mm, wait for       |
|    |     . o        o captured                | Settled, then press      |
|    |  o                                       | Space.                   |
|    +---------------> L (mm)                   |                          |
| Points: 4   slope 0.4123 +/- 0.0011 mm/V      | [ Accept point (Space) ] |
| r^2 0.99998   Residuals: small, no pattern    | [ Remove last (Z) ]      |
| # L (mm)  V (V)   n                           |                          |
| 4 12.00   1.2345  512                         | CONFIDENCE: enough (4/4) |
+-----------------------------------------------+--------------------------+
```

Defaults: five points suggested at evenly spaced lengths; the user may add
more. Continue is enabled at 3 or more points; the panel says "4 points is
enough; more only narrows the slope uncertainty a little".

### 3.3 Step 3 Tare

Purpose: record the empty-hanger voltage (domain.md 3.2).

```
+-----------------------------------------------+--------------------------+
| TARE                                          | NEXT ACTION              |
| Hanger empty, LVDT still.                     | Make sure the hanger is  |
| Live V: 0.0213 V   [Settled]                  | empty and nothing is     |
| Averaging  [ 2 ] s   (default)                | touching it, then press  |
|                                               | Space.                   |
| Tare V   0.0212 V  +/- 0.0003  (n 85000)      |                          |
|                                               | [ Record tare (Space) ]  |
| Previous tare: 0.0210 V at 11:58  [Reuse]     | [ Redo (Z) ]             |
+-----------------------------------------------+--------------------------+
```

Pressing Record again replaces the tare after a one-line confirmation. While
averaging, a progress bar shows seconds left; Esc cancels and keeps the old
tare.

### 3.4 Step 4 Elastic (long specimen)

Purpose: step through loads on the long specimen; fit E from the linear part.

```
+-----------------------------------------------+--------------------------+
| ELASTIC  load step 3 of 6                     | NEXT ACTION              |
| Live dV: 0.0412 V  [Creeping 0.2 mV/s]        | Add the next load gently.    |
|  strain ^                                     | Press Space when Settled.|
|         |      o                              |                          |
|         |   o  o   <- captured                | [ Accept (Space) ]       |
|         +-----------> stress                  | [ Nudge window ([ / ]) ] |
| Load  N     Stress MPa  Strain      Status    |                          |
| 2     1.96  ...         ...         accepted  | CONFIDENCE: building     |
| 3     2.94  (live)      (live)      creeping  |  E ~ 112 GPa +/- 9       |
+-----------------------------------------------+--------------------------+
```

Live-view detail (trace, indicators, guidance placement) is owned by F0B
~KR3SSE1, see [live-view.md](live-view.md). This file fixes only placement: trace and table in the work area,
guidance and confidence in the panel.

### 3.5 Step 5 Plastic (short specimen)

Same layout and keys as Elastic, on the short specimen, run until yield or the
user stops. Differences:

```
+-----------------------------------------------+--------------------------+
| PLASTIC  load step 5                          | NEXT ACTION              |
| Swap to the short specimen: [ Done swapping ] | Load past the knee in    |
| Live dV: 0.2210 V  [Settled]                  | small steps.             |
|  stress ^        _.-- yield?                  |                          |
|         |     .-'                             | [ Accept (Space) ]       |
|         +-----------> strain                  | [ Finish run (F) ]       |
| Yield (0.2% offset): not yet reached          | CONFIDENCE: enough       |
+-----------------------------------------------+--------------------------+
```

A swap prompt precedes capture. The saturation indicator (section 5) matters
most here; on SATURATED the point cannot be accepted and the panel says what
to do (section 6).

### 3.6 Step 6 Results (review screen)

The review screen: every number with its uncertainty, and a way back to fix it.

```
+-----------------------------------------------+--------------------------+
| RESULTS                                       | NEXT ACTION              |
| Young's modulus E   112.4 GPa +/- 4.1 (95%)   | Check the fit looks      |
|   95% interval      108.3 .. 116.5 GPa        | right, then export.      |
|   Confidence: HIGH (plain language below)     |                          |
| Yield strength      212 MPa +/- 9             | [ Export  (Enter) ]      |
|   fit window  points 2..6  [Adjust window]    | [ Back to Elastic ]      |
|  stress ^   o o o o                           |                          |
|         |  o     fit line + 95% band          | Review checklist:        |
|         +-----------> strain                  |  [x] settled each point  |
| Notes: 1 point rejected (creeping), kept      |  [x] no saturation       |
|        in raw data.                           |  [ ] window looks right  |
+-----------------------------------------------+--------------------------+
```

Content is owned by F8 ~9PMPWH8: best value +/- U, 95% interval, one
plain-language sentence ("The data support E between 108 and 117 GPa; more
points would narrow this"). Each row links to the step that produced it.
The checklist is advisory; Export is never blocked by it.

### 3.7 Step 7 Export

```
+-----------------------------------------------+--------------------------+
| EXPORT                                        | NEXT ACTION              |
| Files to write (all selected):                | Choose where to save,    |
|  [x] Results report (.txt)                    | then export.             |
|  [x] Measurements table (.tsv)                |                          |
|  [x] Calibration (lvdt_calibration.txt)       | [ Export  (Enter) ]      |
|  [x] Raw data bundle                          |                          |
| Folder  ~/sadi-data/2026-11-08-A  [Change]    | After export:            |
| Written: report.txt OK  table.tsv OK ...      | [ Start new run ]        |
+-----------------------------------------------+--------------------------+
```

Exports never overwrite; name clashes get a suffix. After success the panel
offers "Start new run" and "Open folder"; closing the app is safe at any time.

## 4. Keyboard map

One key does the main thing. Keys are active only when no text field has focus.

| Key | Action |
|---|---|
| Space | Accept the current capture (point, tare, step) |
| Enter | Press the primary button of the next-action panel |
| Z / Ctrl+Z | Undo last accept or edit |
| Shift+Z / Ctrl+Y | Redo |
| [ and ] | Nudge the fit/settle window start earlier / later by one sample group |
| Shift+[ and Shift+] | Nudge the window end earlier / later |
| Left / Right | Previous / next step (done steps; Expert: any) |
| F | Finish the current phase (asks to confirm) |
| Esc | Cancel an in-progress averaging or dialog |
| ? | Show this map |
| Tab / Shift+Tab | Move focus; order is rail, work area, panel, status bar |

Space never fires while Creeping or Saturated; instead the panel shows why
(section 6) and `Shift+Space` accepts anyway with a "recorded as unsettled"
flag in the data. Undo and redo cover accepts, removals and window nudges,
are unlimited within the session, and never delete raw samples (they change
which are used).

## 5. Status model

Three always-visible indicators, each a word plus a glyph plus (secondary)
colour:

| Indicator | States | Meaning |
|---|---|---|
| Source | `Connected` / `Simulated` | Real device vs simulator. Simulated also puts a banner "SIMULATED DATA" on every screen and in every export. |
| Motion | `Settled` / `Creeping` | From the settle detector (lctt/settle.md), a suggestion only. Creeping shows the drift rate. Unknown (not enough data) shows `Measuring...`. |
| Signal | `Signal OK` / `Near limit` / `SATURATED` | Near limit at 90% of range; SATURATED when the input is at the rail. |

Additional header state: save indicator `Saved 12:04:11` / `Saving...` /
`NOT SAVED` (the last only on a durable-write failure, with the error style of
section 6). A device drop shows `Disconnected` in the Source slot and a
reconnect prompt; data already durable is untouched.

The save indicator is derived read-only from the writer's enqueued and durable
seqs (`sadi.api.save_indicator`, `GET /api/save-indicator`): `Saving...` is
shown as soon as a record is enqueued and not yet durable, so clients polling
every 250 ms (`poll_ms`) show it within 250 ms. `NOT SAVED` latches on writer
failure and never clears.

The web UI has ONE save indicator source: `saveView` (web/src/components/status/saveView.ts)
over the polled backend facts. The status bar and the debug strip both render it.
With no open session it reads `No session` (never `Saved`); with a session it shows
the backend label (`Saved 12:04:11` / `Saving... (n pending)` / `NOT SAVED`); an
unreachable or unrecognised backend answer reads `Save status unknown`. The UI never
stamps its own "saved" time on a write, so it cannot claim durability the writer has
not confirmed.

The debug strip keeps the two seq spaces apart: `WS frame seq` is the
hub-assigned WebSocket frame counter (gaps mean dropped frames), and
`WAL seq (durable / queued)` is the raw WAL seq space (highest durable /
highest enqueued). They are never shown as one number. A faulted device
(`status` error, a device fault, or an acquisition fault) renders as
`(!) fault: <reason>`, never `[ok]`; `GET /api/device/status` reports
`attached=false` for it.

## 6. Error and warning style: say what to do

Format: one line of what happened in plain words, one line of what to do,
then optional [details]. No error codes up front, no jargon, no blame.

```
+----------------------------------------------------------+
| ! The reading is at its limit (saturated).               |
|   Lower the load, then try again.     |
|                                          [Details] [OK]  |
+----------------------------------------------------------+
```

Rules:

- Title states the situation; the second line begins with an imperative verb.
- Severity by word and glyph: `i` info, `!` warning (can continue), `X` error
  (cannot continue). Errors block only the action that failed.
- Inline, next to the thing that is wrong, before any modal. Modals only for
  data-loss risk.
- Every error has a retry or an escape; none ends with a dead screen.
- Details hold the technical message and the log location. They are always
  logged server-side.
- Data-safety failures (disk full, write failed) use the same style and say
  that data already shown as saved is safe.

## 7. Time budget and defaults

Target: a practised user finishes a full run in about 30 minutes; a first-time
student in about 45. Budgets are targets for the usability pass, not timeouts.

| Phase | Budget (practised) | Defaults that skip questions |
|---|---|---|
| Setup | 2 min | device auto-pick, last L0/hanger/folder, run name from date |
| Calibrate | 5 min | five evenly spaced points suggested |
| Tare | 1 min | 2 s averaging, reuse previous tare offered |
| Elastic | 8 min | window auto-chosen, settle suggested |
| Plastic | 8 min | same, plus yield offset 0.2% |
| Results | 3 min | best fit window pre-selected |
| Export | 1 min | all files, run folder |

A question is skipped only when a default exists AND the value is shown on the
screen so it can be changed. Skipped values appear in the report as
"default". The elapsed time per phase is shown quietly in the header and is
logged for the usability pass.

## 8. Confidence and stop-early, without taking control

The confidence indicator lives in the lower half of the next-action panel.
It reports; it never acts.

```
 CONFIDENCE
 Enough data for E:  [########--]  80%   "enough"
 E ~ 112 GPa +/- 9   (95%)
 More points would narrow this by about 2 GPa.
 [ Why? ]
 -------------------------------------------------
 Suggestion: you can stop loading here.   [ Keep going ]  [ Finish phase ]
```

Rules:

- States: `building`, `enough`, `high`. Words first, meter second. The percent
  is a rough guide, labelled as such in [Why?].
- The stop-early suggestion appears as a quiet line in the panel. No modal, no
  sound, no focus change, no auto-advance, no disabling of capture. Capture,
  undo and navigation keep working exactly as before.
- Dismissing "Keep going" hides the suggestion for this phase until the
  estimate changes materially; it is never shown twice in a row for the same
  state.
- The primary button does not change to Finish because of a suggestion; the
  user chooses `F` or the Finish button.
- Why? shows the reasoning in plain language and the numbers behind it (the
  uncertainty target, points so far, expected gain from one more point).
- The same text is available to screen readers as a polite live region
  (section 9), announced at most once per change.
- Guidance engine is PH1 ~G2YNMJB; placement and wording here are binding on
  F12 ~9EFDXQE.

## 9. Accessibility

- Light theme; text contrast at least 4.5:1, large text and UI parts 3:1.
- Never colour alone: every state has a word and a glyph (rail, status bar,
  errors).
- Fully keyboard operable; visible focus ring (2 px, high contrast); logical
  tab order (section 4); no keyboard traps; every shortcut also has a button.
- Semantic landmarks: header, nav (step rail with `aria-current="step"`),
  main, complementary (panel), status bar as `role="status"`.
- Live values update at most once per second for assistive tech; confidence
  and status changes use `aria-live="polite"`; errors use `role="alert"`.
- Plots have a text summary and the data table beside them.
- Minimum 16 px body text, layout holds at 200% zoom; touch targets at least
  40 px.
- No time-limited actions; no flashing; motion limited to the progress bar.

## 10. Usability-pass protocol (used by F14)

Goal: find where a first-time user stalls, errs or loses trust. Run against
the simulator first, then once on hardware (hardware-verification.md).

Participants: at least 5, none of whom built the app; mix of students and
one lab-experienced user. Observer takes notes; the participant thinks aloud.
No help given until the participant asks twice or 2 minutes pass.

Task scripts (each starts from a fresh run unless noted):

| Task | Script | Success criteria |
|---|---|---|
| T1 | "Start a new run with the simulator and enter the specimen." | Setup done unaided in <= 3 min; no wrong field |
| T2 | "Calibrate the LVDT with the gauge blocks." | >= 3 points accepted only when Settled; <= 1 misstep |
| T3 | "Record the tare." | Hanger-empty confirmed; done <= 2 min |
| T4 | "Run the elastic test and stop when you think you have enough." | Participant states why they stopped; saw the confidence panel; stop was their choice |
| T5 | "Run the plastic test to yield." | No point accepted while Saturated; yield reported |
| T6 | "You made a mistake on the last point; fix it." | Undo found <= 30 s |
| T7 | "Read out the modulus and how sure the software is." | States value, unit, uncertainty in own words correctly |
| T8 | "Export and say where the files are." | Folder named correctly |
| T9 | "Unplug the device mid-run (or simulate), then recover." | Recovers with no lost accepted points; error read and followed |

Run-level criteria: full run within 1.5x the section 7 budget for first-timers;
at least 4 of 5 participants complete T1 to T8 unaided; zero data-loss events;
every error message acted on correctly at first read in at least 80% of
occurrences; post-test rating of "I knew what to do next" at least 4 of 5.

Measures per task: completion (yes / yes with help / no), time, errors,
hesitations over 10 s, keys used vs mouse, quotes.

Issue log format (one row per issue, in `docs/usability/<date>-issues.md`,
ASCII table or TSV):

| Field | Content |
|---|---|
| ID | `U-<date>-<nn>` |
| Task | T1..T9 or "general" |
| Step | rail step where it happened |
| Participant | P1..Pn |
| Observation | what happened, in observable terms |
| Severity | 0 cosmetic, 1 slowed, 2 error made, 3 blocked, 4 data risk |
| Evidence | quote, timestamp, screenshot name |
| Cause guess | one line |
| Proposed fix | one line |
| Ticket | frob ticket handle once filed |

Triage: severity 3 and 4 become tickets immediately (bug, high); severity 2
within the same cycle; 0 and 1 batched. Severity 4 stops the pass until
triaged. The pass ends with a short report: criteria met or not, issue counts
by severity, top three changes.

## 11. Open questions

- Whether Expert mode exposes a manual tare entry (domain.md allows it) or
  only free navigation; this file assumes both.
- Exact confidence thresholds for `enough` and `high` come from PH1
  ~G2YNMJB; the wording and placement here do not depend on them.
