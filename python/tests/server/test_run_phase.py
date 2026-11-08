"""Run phase owner: validated forward-only transitions, durable across resume, WS provider."""

# frob:ticket 01M6XAKF5AK7FCJNBHPM62NYRS

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.guidance import Phase
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.server.routes.results import make_guidance_provider
from sadi.server.run_phase import check_transition, fold_phase, next_allowed, phase_record
from sadi.store.events import MarkerEntry
from sadi.store.records import MarkerV1


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the lctt lab and an open session."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "t"}).status_code == 201
        yield c


def _entry(seq: int, label: str, kind: str = "run.phase") -> MarkerEntry:
    """A marker entry for fold tests."""
    return MarkerEntry(seq=seq, marker=MarkerV1(kind=kind, label=label))


# frob:tests python/sadi/server/run_phase.py::check_transition
# frob:tests python/sadi/server/run_phase.py::next_allowed
def test_transitions_only_forward_one_step() -> None:
    """None -> calibrate -> elastic -> plastic; skips, repeats and going back are refused."""
    assert check_transition(None, Phase.CALIBRATE).is_ok
    assert check_transition(None, Phase.ELASTIC).is_err
    assert check_transition(Phase.CALIBRATE, Phase.ELASTIC).is_ok
    assert check_transition(Phase.CALIBRATE, Phase.CALIBRATE).is_err
    assert check_transition(Phase.ELASTIC, Phase.CALIBRATE).is_err
    assert check_transition(Phase.PLASTIC, Phase.PLASTIC).is_err
    assert next_allowed(Phase.PLASTIC) is None


# frob:tests python/sadi/server/run_phase.py::fold_phase
# frob:tests python/sadi/server/run_phase.py::phase_record
def test_fold_ignores_invalid_and_foreign_markers() -> None:
    """Unknown labels, out-of-order and unrelated markers never move the phase."""
    assert fold_phase([]) is None
    got = fold_phase(
        [
            _entry(1, "elastic"),
            _entry(2, "calibrate"),
            _entry(3, "bogus"),
            _entry(4, "plastic", kind="wizard.done"),
            _entry(5, "elastic"),
            _entry(6, "calibrate"),
        ]
    )
    assert got is Phase.ELASTIC
    assert phase_record(Phase.ELASTIC).type == 0x04


# frob:tests python/sadi/server/service.py::SessionService.enter_phase
# frob:tests python/sadi/server/service.py::SessionService.run_phase
def test_rest_enter_and_refuse(client: TestClient) -> None:
    """Old session reports no phase; entering is ordered; bad order is a 409 problem."""
    assert client.get("/api/session/run-phase").json() == {"phase": None, "next_phase": "calibrate"}
    bad = client.post("/api/session/run-phase", json={"phase": "plastic"})
    assert bad.status_code == 409
    assert bad.json()["hint"]
    ok = client.post("/api/session/run-phase", json={"phase": "calibrate"})
    assert ok.json() == {"phase": "calibrate", "next_phase": "elastic"}
    assert client.post("/api/session/run-phase", json={"phase": "calibrate"}).status_code == 409
    assert client.get("/api/session/run-phase").json()["phase"] == "calibrate"


def test_phase_survives_resume(client: TestClient) -> None:
    """The phase is in the append-only log, so closing and resuming keeps it."""
    for p in ("calibrate", "elastic"):
        assert client.post("/api/session/run-phase", json={"phase": p}).status_code == 200
    name = client.get("/api/session").json()["name"]
    assert client.post("/api/session/close").status_code == 204
    assert client.post("/api/sessions/resume", json={"name": name}).status_code == 201
    assert client.get("/api/session/run-phase").json()["phase"] == "elastic"


# frob:tests python/sadi/server/routes/results.py::make_guidance_provider
def test_provider_uses_recorded_phase_else_infers(client: TestClient) -> None:
    """Recorded plastic is sent even without load points; unrecorded sessions fall back."""
    app = client.app
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    provide = make_guidance_provider(app.state.sessions, labs)  # type: ignore[attr-defined]
    before = provide()
    assert before is not None
    assert before.phase is Phase.CALIBRATE
    for p in ("calibrate", "elastic", "plastic"):
        assert client.post("/api/session/run-phase", json={"phase": p}).status_code == 200
    after = provide()
    assert after is not None
    assert after.phase is Phase.PLASTIC
