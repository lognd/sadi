"""Launcher AD3 lifecycle: closed exactly once on every exit path; clean Err when unavailable."""

# frob:ticket 01M6Z52N7A69ET20H5GMS8S7BG
from __future__ import annotations

import signal

import pytest
from fastapi import FastAPI
from typani import Err, Ok

from sadi import launcher
from sadi.bench.ad3 import Ad3Closed, DwfCode, DwfError, launch
from sadi.bench.ad3.fake import FakeDwf
from sadi.bench.ad3.launch import ad3_requested, open_managed_ad3


def _fake() -> FakeDwf:
    return FakeDwf()


def _loader(fake: FakeDwf):  # noqa: ANN202
    return lambda: Ok(Ad3Closed(fake))


def test_ad3_requested_flag_and_env() -> None:
    """frob:tests sadi.bench.ad3.launch.ad3_requested"""
    assert ad3_requested(True, {})
    assert ad3_requested(False, {"SADI_AD3": "Yes"})
    assert not ad3_requested(False, {"SADI_AD3": "0"})


# frob:tests python/sadi/bench/ad3/launch.py::Ad3Guard.__enter__
# frob:tests python/sadi/bench/ad3/launch.py::Ad3Guard.close
def test_guard_closes_on_context_exit_once() -> None:
    """frob:tests sadi.bench.ad3.launch.Ad3Guard"""
    fake = _fake()
    guard = open_managed_ad3(_loader(fake)).unwrap()
    with guard:
        assert guard.session.is_open
    assert not guard.session.is_open and guard.closed
    assert guard.close().is_ok


# frob:tests python/sadi/bench/ad3/launch.py::Ad3Guard.__exit__
def test_guard_closes_on_exception() -> None:
    """frob:tests sadi.bench.ad3.launch.Ad3Guard.__exit__"""
    guard = open_managed_ad3(_loader(_fake())).unwrap()
    with pytest.raises(RuntimeError), guard:
        raise RuntimeError("boom")
    assert not guard.session.is_open


def test_guard_signal_closes_then_exits() -> None:
    """frob:tests sadi.bench.ad3.launch.Ad3Guard.install_signal_handlers"""
    prev = signal.getsignal(signal.SIGTERM)
    guard = open_managed_ad3(_loader(_fake())).unwrap()
    with pytest.raises(SystemExit) as ei:
        signal.raise_signal(signal.SIGTERM)
    assert ei.value.code == 128 + signal.SIGTERM
    assert not guard.session.is_open
    assert signal.getsignal(signal.SIGTERM) == prev


def test_missing_library_is_clean_err() -> None:
    """frob:tests sadi.bench.ad3.launch.open_managed_ad3"""
    err = DwfError(code=DwfCode.LIBRARY_MISSING, detail="no libdwf")
    got = open_managed_ad3(lambda: Err(err))
    assert got.is_err and "library missing" in got.danger_err


def test_open_failure_is_clean_err() -> None:
    """frob:tests sadi.bench.ad3.launch.open_managed_ad3 - no device."""
    closed = Ad3Closed(_fake(), index=99)
    got = open_managed_ad3(lambda: Ok(closed), index=99)
    assert got.is_err and "open failed" in got.danger_err


def test_launcher_closes_ad3_after_serve(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:  # noqa: ANN001
    """frob:tests sadi.launcher.main - --ad3 opens via open_managed_ad3 and closes after serve."""
    fake = _fake()
    guards = []
    real = open_managed_ad3

    def opener():  # noqa: ANN202
        g = real(_loader(fake))
        guards.append(g.unwrap())
        return g

    monkeypatch.setattr(launch, "open_managed_ad3", opener)
    monkeypatch.setattr(launcher, "preflight", lambda *_a: Ok(None))
    monkeypatch.setattr(launcher, "_port_free", lambda *_a: True)

    def serve(_app: FastAPI, _h: str, _p: int) -> None:
        assert guards[0].session.is_open
        raise KeyboardInterrupt

    argv = ["--ad3", "--no-browser", "--data-root", str(tmp_path)]
    assert launcher.main(argv, serve=serve) == 0
    assert not guards[0].session.is_open


def test_launcher_ad3_unavailable_exits_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,  # noqa: ANN001
) -> None:
    """frob:tests sadi.launcher.main - missing libdwf gives EXIT_AD3, not a crash."""
    monkeypatch.setattr(launch, "open_managed_ad3", lambda: Err("ad3 unavailable"))
    monkeypatch.setattr(launcher, "preflight", lambda *_a: Ok(None))
    monkeypatch.setattr(launcher, "_port_free", lambda *_a: True)
    argv = ["--ad3", "--no-browser", "--data-root", str(tmp_path)]
    assert launcher.main(argv, serve=lambda *_a: None) == launcher.EXIT_AD3
