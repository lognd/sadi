# Wizard shell

Status: current

Implements the layout of `docs/ux.md` sections 2, 4, 5 and 6.

- `components/wizard/WizardShell.tsx` loads `GET /api/session/wizard`, renders the step rail,
  the work area (children), the next-action panel, the shortcut list and the status bar, and
  posts `wizard/complete`, `wizard/skip`, `undo`, `redo`. Each write replaces the wizard
  state with the `Committed.wizard` it returns.
- `StepRail`: glyph plus word per step (`[x] [>] [ ] [-]`), `aria-current="step"`. The rail
  comes entirely from the API, so lab-specific steps need no web change.
- `NextActionPanel`: the current step's hint and one big primary button
  (`btn btn-primary`, `data-variant="primary"`) with Skip as `btn btn-secondary`. `src/styles.css`
  (imported once from `main.tsx`) is the shared stylesheet: system fonts, spacing, a
  `:focus-visible` ring (outlines are never removed), and the primary vs secondary button styles.
- `ErrorNotice`: renders a problem+json as "what happened / What to do: hint".
- `components/status/StatusBar.tsx`: Source, Motion, Signal and last-saved time; its inputs are
  props supplied by the run screens (live data arrives with the stream tickets).

## Keyboard

`keys/keymap.ts` is a pure map (`resolveKey`); `keys/useKeyCapture.ts` attaches it to window and
ignores events from text fields, and Enter/Space while a button, link, summary or role=button/link has focus (the control activates instead). Space accepts, Shift+Space accepts unsettled, Enter presses the
primary button, Ctrl+Z / Ctrl+Y undo and redo, `?` toggles the shortcut list, F3 requests `export` (forwarded to `onKeyAction`). Arrows nudge the
window when `nudgeActive` is set (Shift moves the end), else move between steps; `[ ] { }` always
nudge. Shell handles primary/undo/redo/help; other actions go to `onKeyAction`.
The on-screen list (`SHORTCUTS`) lives beside the map.

Not yet: accept/nudge/step navigation behaviour (run and review screens), mode toggle, header.

## Mounting in the app

`App.tsx` renders `screens/WizardHost.tsx`, which maps the current rail step's `phase` to a screen
(`screenFor`): run screens for calibration, tare, elastic and plastic; the review screen for
Results; the export screen for Export (and when no step is current). Each screen is keyed by its
kind so it remounts on a step change, and reports rail changes through `WizardShell.onWizard`.
On Results the review screen owns undo/redo (`delegateUndo`), so a key press is never applied twice.

## Session setup (no open session)

When `GET /api/session/wizard` answers 409 `no_open_session`, `WizardHost` shows
`screens/setup/SessionSetup.tsx` instead of the step rail. It lists `GET /api/sessions` (including
recovered ones) with a Resume button per row (`POST /api/sessions/resume`), and a form (lab from
`GET /api/labs`, specimen name and material) that does `POST /api/sessions`. Data safety: resume
saves a new version and create allocates a new id, so nothing is overwritten or discarded, and the
screen has no delete action. After either succeeds the host reloads the wizard and the rail appears.
The form is plain labelled controls, so Tab/Enter drive it. With no labs registered the form is
disabled and says so.

## Setup step panel

The Setup step renders `ClampCheckPanel` (`screens/setup/`), which reads `GET /api/session/clamp-check`
and captures each cycle as a `setup` phase point. See [clamp check](../lctt/clamp-check.md). Skip
stays available and is never blocked.

## Run-phase sync

The server records the guided-run phase (`GET/POST /api/session/run-phase`; only the next of
calibrate, elastic, plastic is legal, otherwise 409 `bad_phase_transition` with a hint). When
`WizardHost` shows the calibrate, elastic or plastic screen it calls `enterRunPhase`
(`web/src/api/runPhase.ts`): GET first, do nothing if the server is already in or past that phase
(so repeats and reloads show no error), otherwise POST each missing phase in order. A refusal is
shown above the run screen through `ErrorNotice` with the server's hint. Tare is not a server phase.
