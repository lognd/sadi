# Wizard shell

Status: current

Implements the layout of `docs/ux.md` sections 2, 4, 5 and 6.

- `components/wizard/WizardShell.tsx` loads `GET /api/session/wizard`, renders the step rail,
  the work area (children), the next-action panel, the shortcut list and the status bar, and
  posts `wizard/complete`, `wizard/skip`, `undo`, `redo`. Each write replaces the wizard
  state with the `Committed.wizard` it returns.
- `StepRail`: glyph plus word per step (`[x] [>] [ ] [-]`), `aria-current="step"`. The rail
  comes entirely from the API, so lab-specific steps need no web change.
- `NextActionPanel`: the current step's hint and one big primary button.
- `ErrorNotice`: renders a problem+json as "what happened / What to do: hint".
- `components/status/StatusBar.tsx`: Source, Motion, Signal and last-saved time; its inputs are
  props supplied by the run screens (live data arrives with the stream tickets).

## Keyboard

`keys/keymap.ts` is a pure map (`resolveKey`); `keys/useKeyCapture.ts` attaches it to window and
ignores events from text fields. Space accepts, Shift+Space accepts unsettled, Enter presses the
primary button, Ctrl+Z / Ctrl+Y undo and redo, `?` toggles the shortcut list. Arrows nudge the
window when `nudgeActive` is set (Shift moves the end), else move between steps; `[ ] { }` always
nudge. Shell handles primary/undo/redo/help; other actions go to `onKeyAction`.
The on-screen list (`SHORTCUTS`) lives beside the map.

Not yet: accept/nudge/step navigation behaviour (run and review screens), mode toggle, header.
