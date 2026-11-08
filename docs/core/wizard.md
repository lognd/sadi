# Wizard framework

Status: current

Owner: ~XP2D6HY. Code: `python/sadi/core/wizard.py`. Tests: `python/tests/core/test_wizard.py`.

The wizard is a stateless, pure layer over a lab's [`StepSpec`s](lab-modules.md) and the
session's `ReplayState` (see [data safety](../data-safety.md)). It owns no state and does no
I/O: every action returns `Result[Command, WizardError]`, where a `Command` is the WAL records
the caller must append before replaying. `WizardError` is a typani `ErrorSet`; each member's
description is the hint shown in the UI.

## Step state machine

`Wizard.create(steps)` refuses an empty list or duplicate ids. `Wizard.state(replay)` folds the
`wizard.step_done`, `wizard.step_skipped` and `wizard.step_reverted` MARKER records (label =
step id) into a `WizardState`: the first unresolved step is `current`, resolved steps are `done`
or `skipped`, later steps are `locked`. Gating is sequential: a later step (for example Tare)
cannot be completed until every earlier one (Calibrate) is done or skipped explicitly with
`skip`. Out-of-order or unknown markers are not applied and are listed in `anomalies`.

`complete`, `skip` and `revert` return a marker record. `revert` reopens only the most recently
finished step, by appending a compensating marker; earlier markers stay in the log.

### Completion criteria

`StepSpec.min_points` (default 0) is the number of active (non-excluded) points of the step's
phase captured since the previous step resolved. `complete` refuses with `NeedPoints` (a UI
hint) until it is met. The criterion only gates `complete`: `skip`, `revert`, `edit`, `undo`
and `redo` are never blocked, so the operator can always preserve or skip recorded data
(ticket ~E6GGFJZ).

## Step rail

`WizardState.rail` is a tuple of `RailItem(id, title, phase, capture, status, needs_device,
hint)`; `status` is `done`, `skipped`, `current` or `locked`, and a locked item's `hint` names
the step to finish first. `WizardState.finished` is true when nothing is current.

## Data actions

- `capture(replay, point)`: only on a device-capturing current step whose phase matches the
  point (`NoCapture`, `PhaseMismatch` otherwise).
- `edit(replay, target, op, args)`: `exclude`, `include`, `set_window`, `override_input` on an
  existing point, or `set_fit_window` on target `analysis`. Window args are validated first.

## Undo and redo

Undo and redo never rewrite or delete history; they append EDIT records.

- Undo of an edit appends an `undo` edit that supersedes it; redo appends a `redo` edit
  superseding that undo.
- Undo of a captured point appends an `exclude` edit with note `wizard:undo_capture`; the point
  record stays in the WAL. Redo appends an `undo` edit superseding that exclude.
- `history(replay)` folds points and edits in seq order into undo and redo stacks; a new action
  clears redo. `undo` / `redo` act on the last entry (`NothingToUndo` / `NothingToRedo`).
