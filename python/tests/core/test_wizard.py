"""Tests for sadi.core.wizard: gating, rail projection, undo/redo as compensating events."""

# frob:ticket 01M6W7R335N9GPFD4DYXP2D6HY

from __future__ import annotations

from typani import Result

from sadi.core.lab import CaptureKind, StepId, StepSpec
from sadi.core.models import Phase
from sadi.core.wizard import (
    Command,
    StepStatus,
    Wizard,
    WizardError,
)
from sadi.store.events import EditV1, PointV1, PointWindow, ReplayState, replay
from sadi.store.records import NewRecord, Record


def _specs() -> list[StepSpec]:
    def mk(sid: str, phase: Phase, cap: CaptureKind) -> StepSpec:
        return StepSpec(
            id=StepId(sid), title=sid.title(), phase=phase, capture=cap, guidance=lambda _r: "go"
        )

    return [
        mk("calibrate", Phase.CALIBRATION, CaptureKind.DEVICE_POINTS),
        mk("tare", Phase.ELASTIC, CaptureKind.NONE),
        mk("load", Phase.ELASTIC, CaptureKind.DEVICE_POINTS),
    ]


class Log:
    """Test harness: appends commands to an in-memory log and replays it."""

    def __init__(self) -> None:
        self.recs: list[Record] = []
        self.state = ReplayState()

    def apply(self, cmd_result: Result[Command, WizardError]) -> None:
        assert cmd_result.is_ok, cmd_result
        for nr in cmd_result.danger_ok.records:
            self.recs.append(_rec(nr, len(self.recs) + 1))
        self.state = replay(self.recs).danger_ok


def _rec(nr: NewRecord, seq: int) -> Record:
    return Record(type=nr.type, seq=seq, wall_ns=seq, flags=nr.flags, payload=nr.payload, crc=0)


def _wiz() -> Wizard:
    return Wizard.create(_specs()).danger_ok


def _point(pid: str, phase: str = "calibration", **inputs: float) -> PointV1:
    return PointV1(
        point_id=pid,
        phase=phase,
        window=PointWindow(first_raw_seq=1, last_raw_seq=5),
        inputs=dict(inputs),
    )


# frob:tests python/sadi/core/wizard.py::Wizard.create
# frob:tests python/sadi/core/wizard.py::Wizard.__init__
def test_create_rejects_empty_and_duplicates() -> None:
    assert Wizard.create([]).danger_err is WizardError.NoSteps
    s = _specs()[0]
    assert Wizard.create([s, s]).danger_err is WizardError.DuplicateStep


# frob:tests python/sadi/core/wizard.py::Wizard.skip
# frob:tests python/sadi/core/wizard.py::Wizard.state
def test_rail_and_gating() -> None:
    w, log = _wiz(), Log()
    st = w.state(log.state)
    assert [i.status for i in st.rail] == [StepStatus.CURRENT, StepStatus.LOCKED, StepStatus.LOCKED]
    assert st.rail[1].hint
    assert w.complete(log.state, StepId("tare")).danger_err is WizardError.Gated
    assert w.complete(log.state, StepId("nope")).danger_err is WizardError.UnknownStep
    log.apply(w.skip(log.state, StepId("calibrate")))
    st = w.state(log.state)
    assert st.rail[0].status is StepStatus.SKIPPED and st.current == "tare"
    assert w.skip(log.state, StepId("calibrate")).danger_err is WizardError.NotCurrent
    log.apply(w.complete(log.state, StepId("tare")))
    log.apply(w.complete(log.state, StepId("load")))
    assert w.state(log.state).finished


# frob:tests python/sadi/core/wizard.py::Wizard.revert
def test_revert_keeps_history_and_only_latest() -> None:
    w, log = _wiz(), Log()
    assert w.revert(log.state).danger_err is WizardError.NothingToRevert
    log.apply(w.complete(log.state, StepId("calibrate")))
    log.apply(w.complete(log.state, StepId("tare")))
    assert w.revert(log.state, StepId("calibrate")).danger_err is WizardError.NotLatest
    n = len(log.recs)
    log.apply(w.revert(log.state))
    assert len(log.recs) == n + 1
    assert w.state(log.state).current == "tare"


# frob:tests python/sadi/core/wizard.py::Wizard.capture
def test_capture_checks_step_and_phase() -> None:
    w, log = _wiz(), Log()
    assert w.capture(log.state, _point("p", "elastic")).danger_err is WizardError.PhaseMismatch
    log.apply(w.capture(log.state, _point("p")))
    assert len(log.state.points) == 1
    log.apply(w.complete(log.state, StepId("calibrate")))
    assert w.capture(log.state, _point("q", "elastic")).danger_err is WizardError.NoCapture


# frob:tests python/sadi/core/wizard.py::Wizard.capture
# frob:ticket 01M6X6PW1F4HNNFMMY5YV3QKP9
def test_capture_accepts_specimen_point_on_any_device_step() -> None:
    w, log = _wiz(), Log()
    log.apply(w.capture(log.state, _point("s", "specimen")))
    assert len(log.state.points) == 1
    log.apply(w.complete(log.state, StepId("calibrate")))
    assert w.capture(log.state, _point("t", "specimen")).danger_err is WizardError.NoCapture


# frob:tests python/sadi/core/wizard.py::Wizard.history
# frob:tests python/sadi/core/wizard.py::Wizard.undo
def test_undo_redo_point_capture_never_deletes() -> None:
    w, log = _wiz(), Log()
    assert w.undo(log.state).danger_err is WizardError.NothingToUndo
    log.apply(w.capture(log.state, _point("p1")))
    log.apply(w.capture(log.state, _point("p2")))
    log.apply(w.undo(log.state))
    assert len(log.state.points) == 2  # history intact
    view = log.state.view()
    assert [p.excluded for p in view.points] == [False, True]
    h = w.history(log.state)
    assert len(h.undo) == 1 and len(h.redo) == 1
    log.apply(w.redo(log.state))
    assert [p.excluded for p in log.state.view().points] == [False, False]
    log.apply(w.undo(log.state))
    log.apply(w.redo(log.state))
    log.apply(w.undo(log.state))
    log.apply(w.undo(log.state))
    assert [p.excluded for p in log.state.view().points] == [True, True]
    assert not log.state.view().anomalies


# frob:tests python/sadi/core/wizard.py::Wizard.redo
def test_undo_redo_edit_and_window_change() -> None:
    w, log = _wiz(), Log()
    log.apply(w.capture(log.state, _point("p", volts=1.0, height=0.01)))
    log.apply(w.edit(log.state, "p", "set_window", {"last_raw_seq": 9}))
    log.apply(w.edit(log.state, "p", "override_input", {"volts": 2.0}))
    cur = log.state.view().points[0]
    assert cur.window.last_raw_seq == 9 and cur.inputs == {"volts": 2.0, "height": 0.01}
    log.apply(w.undo(log.state))
    cur = log.state.view().points[0]
    assert cur.window.last_raw_seq == 9 and cur.inputs == {"volts": 1.0, "height": 0.01}
    log.apply(w.undo(log.state))
    assert log.state.view().points[0].window.last_raw_seq == 5
    log.apply(w.redo(log.state))
    assert log.state.view().points[0].window.last_raw_seq == 9
    # a new action clears the redo history
    log.apply(w.edit(log.state, "p", "exclude"))
    assert w.redo(log.state).danger_err is WizardError.NothingToRedo
    assert len(log.state.edits) == 6
    assert not log.state.view().anomalies


# frob:tests python/sadi/core/wizard.py::Wizard.edit
def test_edit_validation() -> None:
    w, log = _wiz(), Log()
    assert w.edit(log.state, "ghost", "exclude").danger_err is WizardError.UnknownPoint
    log.apply(w.capture(log.state, _point("p")))
    assert w.edit(log.state, "p", "undo").danger_err is WizardError.BadEdit
    assert w.edit(log.state, "p", "set_fit_window").danger_err is WizardError.BadEdit
    assert w.edit(log.state, "analysis", "exclude").danger_err is WizardError.BadEdit
    bad = w.edit(log.state, "p", "set_window", {"first_raw_seq": 99})
    assert bad.danger_err is WizardError.BadWindow
    log.apply(w.edit(log.state, "analysis", "set_fit_window", {"lo": 1, "hi": 2}))
    assert log.state.view().analysis["fit_window"] == {"lo": 1, "hi": 2}
    log.apply(w.undo(log.state))
    assert "fit_window" not in log.state.view().analysis
    assert isinstance(log.state.edits[0].edit, EditV1)


# frob:tests python/sadi/core/wizard.py::WizardState.finished
# frob:tests python/sadi/core/wizard.py::History.can_undo
# frob:tests python/sadi/core/wizard.py::History.can_redo
def test_flags_finished_can_undo_can_redo() -> None:
    w, log = _wiz(), Log()
    assert not w.state(log.state).finished
    assert not w.history(log.state).can_undo and not w.history(log.state).can_redo
    log.apply(w.capture(log.state, _point("p")))
    assert w.history(log.state).can_undo
    log.apply(w.undo(log.state))
    assert w.history(log.state).can_redo
    for sid in ("calibrate", "tare", "load"):
        log.apply(w.skip(log.state, StepId(sid)))
    assert w.state(log.state).finished


# frob:ticket 01M6WJB330TVRVWW639E6GGFJZ
# frob:tests python/sadi/core/wizard.py::Wizard.complete
def test_complete_requires_min_points_but_skip_never_blocked() -> None:
    base = _specs()
    specs = [base[0].model_copy(update={"min_points": 1}), *base[1:]]
    wiz = Wizard.create(specs).danger_ok
    log = Log()
    assert wiz.complete(log.state, StepId("calibrate")).danger_err is WizardError.NeedPoints
    log.apply(wiz.capture(log.state, _point("p1")))
    log.apply(wiz.undo(log.state))  # excludes p1 -> criterion unmet again
    assert wiz.complete(log.state, StepId("calibrate")).danger_err is WizardError.NeedPoints
    log.apply(wiz.capture(log.state, _point("p2")))
    assert wiz.complete(log.state, StepId("calibrate")).is_ok
    log2 = Log()
    log2.apply(wiz.skip(log2.state, StepId("calibrate")))
    assert wiz.state(log2.state).current == StepId("tare")


# frob:ticket 01M6WJB330TVRVWW639E6GGFJZ
# frob:tests python/sadi/core/wizard.py::Wizard.complete
def test_min_points_ignores_points_before_previous_step() -> None:
    base = _specs()
    specs = [
        base[0],
        base[1],
        base[2].model_copy(update={"min_points": 1, "phase": Phase.CALIBRATION}),
    ]
    wiz = Wizard.create(specs).danger_ok
    log = Log()
    log.apply(wiz.capture(log.state, _point("p1")))
    log.apply(wiz.complete(log.state, StepId("calibrate")))
    log.apply(wiz.complete(log.state, StepId("tare")))
    assert wiz.complete(log.state, StepId("load")).danger_err is WizardError.NeedPoints
