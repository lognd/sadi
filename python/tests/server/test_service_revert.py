"""SessionService construction and revert: reopening a step never loses recorded data."""

# frob:ticket 01M6XBHBTGXTE4TT5A9BE5FMFS

from __future__ import annotations

from pathlib import Path

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.schemas import CaptureBody, SessionCreate
from sadi.server.service import SessionService
from sadi.store.events import recover_state

WINDOW = {"first_raw_seq": 1, "last_raw_seq": 5}


def _service(root: Path) -> SessionService:
    """Service over `root` with the lctt lab registered."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    return SessionService(root, labs)


# frob:tests python/sadi/server/service.py::SessionService.__init__
def test_new_service_has_no_open_session_and_lists_labs(tmp_path: Path) -> None:
    """A fresh service holds no session and serves the registered labs."""
    svc = _service(tmp_path)
    assert [lab.id for lab in svc.labs()] == ["lctt"]
    assert svc.list_sessions() == []
    assert svc.wizard_state().is_err  # nothing open


# frob:tests python/sadi/server/service.py::SessionService.revert
def test_revert_reopens_latest_step_and_keeps_all_data(tmp_path: Path) -> None:
    """Revert appends a marker only: the point and prior history survive, on disk too."""
    svc = _service(tmp_path)
    info = svc.create(SessionCreate(lab="lctt", slug="rv"))
    assert info.is_ok, info
    # nothing finished yet: revert is refused and writes nothing
    assert svc.revert(None).is_err

    assert svc.skip("setup").is_ok
    body = CaptureBody.model_validate(
        {"phase": "calibration", "inputs": {"volts": 1.0, "height": 0.01}, "window": WINDOW}
    )
    assert svc.capture(body).is_ok
    for volts, height in ((2.0, 0.02), (3.1, 0.03)):
        extra = CaptureBody.model_validate(
            {"phase": "calibration", "inputs": {"volts": volts, "height": height}, "window": WINDOW}
        )
        assert svc.capture(extra).is_ok
    done = svc.complete("calibrate")
    assert done.is_ok, done
    assert done.danger_ok.wizard.current != "calibrate"
    before_seq = done.danger_ok.seq

    # naming a step that is not the latest finished one is refused
    assert svc.revert("setup").is_err

    rev = svc.revert(None)
    assert rev.is_ok, rev
    assert rev.danger_ok.seq > before_seq
    assert rev.danger_ok.wizard.current == "calibrate"
    pts = svc.points()
    assert pts.is_ok and len(pts.danger_ok) == 3

    assert svc.close().is_ok
    state = recover_state(tmp_path / "sessions" / info.danger_ok.name).danger_ok
    assert len(state.points) == 3
