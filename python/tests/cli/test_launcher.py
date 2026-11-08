"""Tests for the `sadi` launcher."""

# frob:ticket 01M6WMGMM1BP37GS27VRRX9AYP
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typani import Err, Ok

from sadi import launcher
from sadi.store.lock import acquire


def _ok(*_a: object) -> object:
    return Ok(None)


def _enter(app: FastAPI, _host: str, _port: int) -> None:
    """Fake server: run the app lifespan like uvicorn would."""
    with TestClient(app):
        pass


def test_mount_web_serves_index(tmp_path: Path) -> None:
    """frob:tests sadi.launcher.mount_web"""
    (tmp_path / "index.html").write_text("<html>hi</html>")
    app = FastAPI()
    assert launcher.mount_web(app, tmp_path)
    assert "hi" in TestClient(app).get("/").text


def test_mount_web_absent(tmp_path: Path) -> None:
    """Missing dist is not an error; nothing is mounted."""
    assert not launcher.mount_web(FastAPI(), tmp_path / "nope")


def test_serve_default_host_and_lock_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frob:tests sadi.launcher.main - bare `sadi` serves on 127.0.0.1 and exits 0."""
    monkeypatch.setattr(launcher, "preflight", _ok)
    monkeypatch.setattr(launcher, "_port_free", lambda *_a: True)
    seen: list[tuple[str, int]] = []

    def serve(app: FastAPI, host: str, port: int) -> None:
        seen.append((host, port))
        _enter(app, host, port)

    assert launcher.main(["--data-root", str(tmp_path), "--no-browser"], serve) == 0
    assert seen == [("127.0.0.1", 8000)]


def test_refused_lock_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A live lock is never stolen; the launcher exits non-zero with the hint."""
    monkeypatch.setattr(launcher, "preflight", _ok)
    held = acquire(tmp_path, recover_stale=False)
    assert held.is_ok
    try:
        code = launcher.main(["serve", "--data-root", str(tmp_path), "--no-browser"], _enter)
    finally:
        held.danger_ok.release()
    assert code == launcher.EXIT_LOCK
    assert "cannot lock data root" in capsys.readouterr().err


def test_preflight_failure_blocks_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A doctor blocker prints its report and the server is never started."""
    monkeypatch.setattr(launcher, "preflight", lambda *_a: Err("STEP 1: fix it\n"))
    called: list[int] = []

    def serve(_a: FastAPI, _h: str, _p: int) -> None:
        called.append(1)

    code = launcher.main(["serve", "--data-root", str(tmp_path), "--no-browser"], serve)
    assert code == launcher.EXIT_PREFLIGHT
    assert not called
    assert "STEP 1: fix it" in capsys.readouterr().err


def test_doctor_passthrough(monkeypatch: pytest.MonkeyPatch) -> None:
    """`sadi doctor ...` forwards its arguments to the doctor CLI."""
    got: list[list[str]] = []

    def fake(argv: list[str]) -> int:
        got.append(argv)
        return 0

    monkeypatch.setattr(launcher, "doctor_main", fake)
    assert launcher.main(["doctor", "list"]) == 0
    assert got == [["list"]]


def test_preflight_blocker_is_err(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """frob:tests sadi.launcher.preflight"""
    monkeypatch.setattr(launcher, "exit_code", lambda _r: 2)
    monkeypatch.setattr(launcher, "render", lambda _r: "REPORT")
    monkeypatch.setattr(launcher, "run", lambda _o: Ok(object()))
    got = launcher.preflight(tmp_path, 8000)
    assert got.is_err
    assert got.danger_err == "REPORT"


def test_pick_port_prefers_then_falls_back() -> None:
    """frob:tests sadi.launcher.pick_port - busy preferred port falls back unless strict."""
    import socket

    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        port = busy.getsockname()[1]
        got = launcher.pick_port("127.0.0.1", port, strict=False)
        assert got.is_ok
        assert got.danger_ok != port
        assert launcher.pick_port("127.0.0.1", port, strict=True).is_err
    assert launcher.pick_port("127.0.0.1", port, strict=True).is_ok


def test_non_loopback_host_rejected(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """frob:tests sadi.launcher.is_loopback - non-loopback host is refused without the override."""
    assert launcher.is_loopback("127.0.0.1")
    assert launcher.is_loopback("localhost")
    assert not launcher.is_loopback("0.0.0.0")
    called: list[int] = []
    code = launcher.main(
        ["--host", "0.0.0.0", "--data-root", str(tmp_path), "--no-browser"],
        lambda *_a: called.append(1),
    )
    assert code == launcher.EXIT_USAGE
    assert not called
    assert "loopback" in capsys.readouterr().err


def test_data_dir_alias_and_printed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """frob:tests sadi.launcher.default_data_dir - --data-dir works and the dir is printed."""
    monkeypatch.setattr(launcher, "preflight", _ok)
    assert launcher.main(["--data-dir", str(tmp_path), "--no-browser"], _enter) == 0
    assert str(tmp_path) in capsys.readouterr().out
    assert launcher.default_data_dir().name.lower() == "sadi"


def test_default_data_dir_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """The built-in fallback is used when platformdirs is missing."""
    import sys

    monkeypatch.setitem(sys.modules, "platformdirs", None)
    assert launcher.default_data_dir().name == "sadi"


def test_ctrl_c_is_graceful_and_releases_lock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """frob:tests sadi.launcher.main - KeyboardInterrupt after shutdown exits 0, lock free."""
    monkeypatch.setattr(launcher, "preflight", _ok)

    def serve(app: FastAPI, host: str, port: int) -> None:
        _enter(app, host, port)
        raise KeyboardInterrupt

    assert launcher.main(["--data-root", str(tmp_path), "--no-browser"], serve) == 0
    again = acquire(tmp_path, recover_stale=False)
    assert again.is_ok
    again.danger_ok.release()


def test_open_browser_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """frob:tests sadi.launcher.open_browser - failures become Err."""

    def boom(_u: str) -> bool:
        raise OSError("no display")

    monkeypatch.setattr(launcher.webbrowser, "open", boom)
    assert launcher.open_browser("http://x/").is_err
    monkeypatch.setattr(launcher.webbrowser, "open", lambda _u: False)
    assert launcher.open_browser("http://x/").is_err
    monkeypatch.setattr(launcher.webbrowser, "open", lambda _u: True)
    assert launcher.open_browser("http://x/").is_ok


def test_browser_opened_unless_suppressed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """frob:tests sadi.launcher.schedule_browser - the URL is opened once the port listens."""
    import socket

    opened: list[str] = []
    monkeypatch.setattr(launcher, "open_browser", lambda u: opened.append(u) or Ok(None))
    with socket.socket() as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen()
        port = srv.getsockname()[1]
        launcher.schedule_browser("127.0.0.1", port).join(5)
    assert opened == [f"http://127.0.0.1:{port}/"]


def test_selftest_exit_codes(monkeypatch: pytest.MonkeyPatch) -> None:
    """frob:tests sadi.launcher.selftest - success exits 0, failure exits non-zero."""
    monkeypatch.setattr(launcher, "selftest", lambda: Ok(10))
    assert launcher.main(["--selftest"]) == 0
    monkeypatch.setattr(launcher, "selftest", lambda: Err("boom"))
    assert launcher.main(["--selftest"]) == launcher.EXIT_SELFTEST


def test_selftest_reports_missing_binding(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing or broken simulator is an Err."""
    from sadi.doctor import devprobe

    monkeypatch.setattr(
        devprobe, "probe_sim", lambda: devprobe.SimFacts(binding_ok=False, detail="x")
    )
    assert launcher.selftest().is_err
    monkeypatch.setattr(devprobe, "probe_sim", lambda: devprobe.SimFacts(packets=5))
    assert launcher.selftest().danger_ok == 5


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    """frob:tests sadi.launcher.package_version - --version prints and exits 0."""
    assert launcher.main(["--version"]) == 0
    assert capsys.readouterr().out.startswith("sadi ")


class _FakeDevice:
    """Stand-in for a simulator DeviceService."""

    status = "simulated"
    fault = None
    closed = False

    def close(self) -> None:
        """Record shutdown."""
        _FakeDevice.closed = True


def test_sim_requested_flag_and_env() -> None:
    """frob:tests sadi.launcher.sim_requested - flag or SADI_SIM enables the simulator."""
    assert launcher.sim_requested(True, {})
    assert launcher.sim_requested(False, {"SADI_SIM": "1"})
    assert not launcher.sim_requested(False, {"SADI_SIM": "0"})
    assert not launcher.sim_requested(False, {})


def test_sim_flag_injects_device(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """frob:tests sadi.launcher.main - --sim passes the simulator device via AppSettings."""
    seen: list[object] = []
    _FakeDevice.closed = False

    def fake_serve(app: FastAPI, _h: str, _p: int) -> None:
        seen.append(app.state.settings.device)

    monkeypatch.setattr(launcher, "open_sim_device", lambda: Ok(_FakeDevice()))
    argv = [
        "--sim",
        "--skip-preflight",
        "--no-browser",
        "--port",
        "0",
        "--data-root",
        str(tmp_path),
    ]
    assert launcher.main(argv, serve=fake_serve) == 0
    assert isinstance(seen[0], _FakeDevice)
    assert _FakeDevice.closed


def test_no_sim_means_no_device(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Without --sim or SADI_SIM no device is injected."""
    monkeypatch.delenv("SADI_SIM", raising=False)
    seen: list[object] = []

    def fake_serve(app: FastAPI, _h: str, _p: int) -> None:
        seen.append(app.state.settings.device)

    argv = ["--skip-preflight", "--no-browser", "--port", "0", "--data-root", str(tmp_path)]
    assert launcher.main(argv, serve=fake_serve) == 0
    assert seen == [None]


def test_sim_open_failure_exits_device(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A failing simulator open exits EXIT_DEVICE without serving."""
    monkeypatch.setattr(launcher, "open_sim_device", lambda: Err("no sadi_py"))
    argv = [
        "--sim",
        "--skip-preflight",
        "--no-browser",
        "--port",
        "0",
        "--data-root",
        str(tmp_path),
    ]
    assert launcher.main(argv, serve=_enter) == launcher.EXIT_DEVICE


def test_python_dash_m_sadi() -> None:
    """frob:tests sadi.__main__ - `python -m sadi --version` runs the launcher."""
    import subprocess
    import sys

    res = subprocess.run(
        [sys.executable, "-m", "sadi", "--version"], capture_output=True, text=True, check=False
    )
    assert res.returncode == 0
    assert res.stdout.startswith("sadi ")


def test_open_sim_device_real_simulator_streams_samples() -> None:
    """frob:tests sadi.launcher.open_sim_device

    Uses the real built `sadi_py` simulator (skipped when it is not importable).
    """
    pytest.importorskip("sadi_py")
    opened = launcher.open_sim_device()
    assert opened.is_ok
    svc = opened.danger_ok
    try:
        assert svc.start_streaming().is_ok
        block = svc.next_block(timeout=5.0)
        assert block.is_ok
        assert block.danger_ok is not None
        assert block.danger_ok.n_samples > 0
        assert svc.stop_streaming().is_ok
    finally:
        svc.close()


def test_launcher_app_serves_builtin_labs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """frob:tests sadi.launcher.load_builtin_plugins - launcher-built app lists lctt."""
    monkeypatch.setattr(launcher, "preflight", _ok)
    monkeypatch.setattr(launcher, "_port_free", lambda *_a: True)
    bodies: list[object] = []

    def serve(app: FastAPI, _host: str, _port: int) -> None:
        with TestClient(app) as client:
            res = client.get("/api/labs")
            assert res.status_code == 200
            bodies.append(res.json())

    assert launcher.main(["--data-root", str(tmp_path), "--no-browser"], serve) == 0
    assert bodies
    assert "lctt" in str(bodies[0])


def test_load_builtin_plugins_failure_is_surfaced(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """frob:tests sadi.launcher.load_builtin_plugins - a broken source warns, never raises."""

    class Broken:
        name = "builtin"

        def discover(self) -> object:
            raise RuntimeError("boom")

    monkeypatch.setattr(launcher, "builtin_source", Broken)
    plugins, labs = launcher.load_builtin_plugins()
    assert labs.ids() == []
    assert plugins.source_errors()
    assert "warning" in capsys.readouterr().err
