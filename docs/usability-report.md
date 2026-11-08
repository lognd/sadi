# Usability report (F0 walkthrough)

Status: current

Parent: [Documentation index](index.md). Ticket: ~W5XJBZT. Related: [Browser e2e](e2e.md), [UX](ux.md).
Per-screen notes live next to the code: `web/src/screens/setup/SessionSetup.usability.md`,
`web/src/screens/run/RunScreen.usability.md`, `web/src/screens/review/ReviewScreen.usability.md`,
`web/src/screens/export/ExportScreen.usability.md`.

## Method

Scripted Playwright (chromium) walkthrough against `sadi --sim` on a free port with a temp data
dir, built `web/dist` from the working tree (a stale dist is itself a trap, see U-09). The script
timed each stage and listed the Tab order (20-25 stops per screen) with the focus indicator.
Severity: 1 = blocks or confuses the run, 2 = slows or irritates, 3 = polish.

## Timing (cold start to exported CSV, simulator)

| Stage | Elapsed |
| --- | --- |
| Backend ready (process start to `/openapi.json`) | 2.4 s |
| Session created, wizard mounted | 7.3 s |
| LVDT calibration, 3 points | about 36 s |
| Tare, 1 point | about 13 s |
| Elastic, 1 point | about 11 s |
| Plastic, 3 points | about 24 s |
| Results then Export, CSV downloaded | about 19 s |
| Total | about 118 s |

Most of the run is waiting for the settle detector (about 10 s per point). The operator time is
dominated by that, not by the UI.

## Keyboard-only findings

Tab reaches every control with a visible focus ring, and Tab order follows reading order. Enter
and Space, however, do not activate a focused button or link (U-01).

## Issues

| Id | Sev | Screen | Issue | Status |
| --- | --- | --- | --- | --- |
| U-01 | 1 | all | Enter/Space on a Tab-focused button or link fires the wizard hotkey (complete step / accept) and is `preventDefault`ed, so the control never activates. Repro: LVDT step, Tab x3 to "Mark load change", Enter: the step completes with no points. Skip, Download and Edit/Exclude are unusable by keyboard alone. | Ticketed ~0MZ866N (fix is in `web/src/keys/**`, outside this ticket's scope) |
| U-02 | 2 | review | Edit/Exclude buttons are labelled with raw point UUIDs ("Edit 45ebf721-..."); a screen reader or a Tab user cannot tell rows apart. Use the capture index and load. | Fixed ~81EQRYA (labels use the capture index) |
| U-03 | 2 | review | Tab order walks 2 buttons per point (16+ stops) before reaching the Finish button; no skip link. | Fixed ~81EQRYA (Skip to Finish link) and ~F5JD036 (one Tab stop per point row, arrows switch Edit/Exclude) |
| U-04 | 2 | run | Hotkeys are ignored in text fields, so a typist must Tab off the field before Space accepts; nothing says so. | open |
| U-05 | 2 | run | "Mark load change" is required before Settled ever shows (docs/e2e.md); the operator is not told to press it. | Fixed ~81EQRYA (phase text and hint beside the button) |
| U-06 | 2 | run | After Enter on a step with zero points the run advances silently and shows "Stopped: device_fault" in the message line; the wording does not say what to do. | fixed (~BJVWSNR) |
| U-07 | 2 | setup | "Setup: Clamp slip check" has no capture UI; the only ways forward are "Finish" and "Skip", and the text does not say what the check is. | open |
| U-08 | 3 | export | Two figure buttons per format and the PNG-resolution select come before the CSV link; the primary deliverable is second in Tab order. | open |
| U-09 | 3 | all | A `web/dist` older than the source gives a 422 on skip/complete (step id not sent) with no hint to rebuild. | Fixed ~81EQRYA (a bare 422 now shows a rebuild-web/dist hint) |
| U-10 | 3 | all | The step rail is plain text and not focusable; the Doctor button is last in Tab order. | open |
| U-11 | 3 | all | The unstyled layout (default fonts, no spacing) makes the primary button visually equal to Skip. | open |

## Severity-1 status

U-01 is the only severity-1 issue. It is ticketed (~0MZ866N) rather than fixed here because
the key handling is in `web/src/keys/`, outside the allowed scope of this ticket.
