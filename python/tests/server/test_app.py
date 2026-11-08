"""Tests for the FastAPI app factory."""

# frob:ticket 01M6WKQCC4HJ5C8HXP946BRKXW
# frob:ticket 01M6WK31FEG5BZNZNZHVQ3HMMX

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sadi.plugins import PluginRegistry
from sadi.plugins.builtin import builtin_source
from sadi.server.app import AppSettings, create_app


def _client() -> TestClient:
    reg = PluginRegistry.discover([builtin_source()])
    return TestClient(create_app(AppSettings(registry=reg, data_root=Path("x"))))


def test_plugins_route_reachable() -> None:
    """GET /api/plugins is served through create_app."""
    res = _client().get("/api/plugins")
    assert res.status_code == 200
    assert isinstance(res.json(), list)


def test_doctor_route_reachable() -> None:
    """POST of an unknown doctor check id is routed and answers 404 from the doctor router."""
    res = _client().post("/api/doctor/no-such-check/run")
    assert res.status_code == 404
    assert "detail" in res.json()


def test_unknown_route_404() -> None:
    """An unmounted path returns 404."""
    assert _client().get("/api/nope").status_code == 404


def test_settings_injected_and_no_shared_state() -> None:
    """Each app carries its own settings."""
    a = create_app(AppSettings(data_root=Path("a")))
    b = create_app(AppSettings(data_root=Path("b")))
    assert a.state.settings.data_root == Path("a")
    assert b.state.settings.data_root == Path("b")


def test_lifespan_holds_lock_and_releases(tmp_path: Path) -> None:
    """The app holds the data-root lock while running and frees it on shutdown."""
    from sadi.store.lock import acquire

    app = create_app(AppSettings(data_root=tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/root-lock").json() == {"ok": True}
        assert acquire(tmp_path).is_err
    again = acquire(tmp_path)
    assert again.is_ok
    again.danger_ok.release()


def test_startup_fails_when_lock_held(tmp_path: Path) -> None:
    """A live lock makes startup raise RootLockStartupError and is never stolen."""
    import pytest

    from sadi.server.app import RootLockStartupError
    from sadi.store.lock import LockHeld, acquire

    held = acquire(tmp_path)
    assert held.is_ok
    try:
        with (
            pytest.raises(RootLockStartupError) as info,
            TestClient(create_app(AppSettings(data_root=tmp_path))),
        ):
            pass
        assert isinstance(info.value.failure.error, LockHeld)
        assert held.danger_ok.held
    finally:
        held.danger_ok.release()


def test_degraded_start_reports_lock_failure(tmp_path: Path) -> None:
    """With require_root_lock=False the app starts and /api/root-lock shows the refusal."""
    from sadi.store.lock import acquire

    held = acquire(tmp_path)
    assert held.is_ok
    try:
        app = create_app(AppSettings(data_root=tmp_path, require_root_lock=False))
        with TestClient(app) as client:
            body = client.get("/api/root-lock").json()
        assert body["ok"] is False
        assert body["kind"] == "LockHeld"
    finally:
        held.danger_ok.release()


class _FakeWriter:
    """Minimal failable seq source standing in for WriterHandle."""

    def __init__(self) -> None:
        self.durable_seq = 0
        self.enqueued_seq = 0
        self.listeners: list = []

    def on_failure(self, listener) -> None:  # type: ignore[no-untyped-def]
        self.listeners.append(listener)


# frob:ticket 01M6WMJZPYNHZR0KHY2C6W07WH
# frob:tests python/sadi/server/app.py::create_app
# frob:tests python/sadi/api/save_indicator.py::FailableSeqSource.on_failure
def test_save_indicator_reachable_and_latches_on_failure() -> None:
    """GET /api/save-indicator is served, and a writer failure latches NOT SAVED."""
    from sadi.store.writer_thread import Stalled

    writer = _FakeWriter()
    client = TestClient(create_app(AppSettings(writer=writer, require_root_lock=False)))
    assert client.get("/api/save-indicator").json()["state"] == "saved"
    writer.enqueued_seq = 2
    assert client.get("/api/save-indicator").json()["state"] == "saving"
    assert len(writer.listeners) == 1
    writer.listeners[0](Stalled(waited_s=1.0, durable_seq=0, enqueued_seq=2))
    body = client.get("/api/save-indicator").json()
    assert body["state"] == "not_saved"
    assert body["label"] == "NOT SAVED"
