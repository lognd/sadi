"""SIGKILL the whole app mid-WAL-write while MC/GP workers run: the session must recover."""

# frob:ticket 01M6W7RAY4KTF866Q0Y7B4SZGG
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest
from crash import harness

from sadi.jobs.tasks.mc import mc_steps
from sadi.logging_setup import get_logger

_log = get_logger("tests.concurrency.kill_with_jobs")

CRASHEE = Path(__file__).resolve().parent / "jobs_crashee.py"
SEEDS = range(int(os.environ.get("SADI_CONC_KILL_SEEDS", "3")))
DEADLINE_S = 60.0
ACKS_AFTER_JOBS = 5
MAX_RECORDS = 20_000


def _wait_for(pred, what: str, proc: subprocess.Popen[bytes]) -> None:  # type: ignore[no-untyped-def]
    """Poll `pred` until true or the deadline; fail loudly (never sleep as synchronisation)."""
    deadline = time.monotonic() + DEADLINE_S
    while time.monotonic() < deadline:
        if pred():
            return
        if proc.poll() is not None:
            pytest.fail(f"crashee exited early (rc={proc.returncode}) before {what}")
        time.sleep(0.002)
    proc.kill()
    pytest.fail(f"timed out waiting for {what}")


def _oracle_lines(path: Path) -> list[str]:
    """Complete oracle lines so far (a torn tail is dropped)."""
    if not path.exists():
        return []
    return path.read_bytes().decode("ascii", errors="replace").split("\n")[:-1]


def _pid_gone(pid: int) -> bool:
    """True once `pid` no longer exists or is a zombie."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


def _run(tmp_path: Path, seed: int, mode: str) -> tuple[harness.Run, list[int]]:
    """Launch the crashee, kill it per `mode`, and return its Run plus the worker pids."""
    root = tmp_path / "root"
    root.mkdir()
    oracle = tmp_path / "oracle.log"
    env = dict(os.environ)
    pkg_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = pkg_root + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [sys.executable, str(CRASHEE), str(root), str(oracle), str(seed), mode, str(MAX_RECORDS)]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for(lambda: "jobs_progressing" in _oracle_lines(oracle), "jobs progressing", proc)
        if mode == "external":
            base = harness.parse_oracle(oracle).max_ack
            _wait_for(
                lambda: harness.parse_oracle(oracle).max_ack >= base + ACKS_AFTER_JOBS,
                "acks after jobs started",
                proc,
            )
            proc.kill()
        rc = proc.wait(timeout=DEADLINE_S)
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    lines = _oracle_lines(oracle)
    pids = [int(ln.split()[1]) for ln in lines if ln.startswith("worker_pid ")]
    parsed = harness.parse_oracle(oracle)
    _log.info("seed=%d mode=%s rc=%d max_ack=%d pids=%s", seed, mode, rc, parsed.max_ack, pids)
    return harness.Run(root, oracle, seed, rc, parsed), pids


# frob:tests python/tests/concurrency/jobs_crashee.py::main
# frob:tests python/sadi/store/wal.py::WalWriter.append_batch
@pytest.mark.parametrize("mode", ["external", "self"])
@pytest.mark.parametrize("seed", SEEDS)
def test_kill_mid_write_while_jobs_run(tmp_path: Path, seed: int, mode: str) -> None:
    """Acked records survive, no torn state, workers do not outlive the app, jobs rerun from raw."""
    run, pids = _run(tmp_path, seed, mode)
    assert run.returncode != 0, "crashee must have died, not exited cleanly"
    assert not run.oracle.clean_exit
    assert run.oracle.max_ack >= 1
    assert harness.verify_recovery(run) == []
    sdir = harness.session_dirs(run.root)[0]
    stray = [p.name for p in sdir.rglob("*") if "job" in p.name.lower()]
    assert stray == [], "jobs must not persist state into the session"
    assert pids, "workers must have been spawned"
    deadline = time.monotonic() + DEADLINE_S
    while time.monotonic() < deadline and not all(_pid_gone(p) for p in pids):
        time.sleep(0.01)
    assert all(_pid_gone(p) for p in pids), "orphaned worker processes survived the kill"


# frob:tests python/sadi/jobs/tasks/mc.py::mc_steps
def test_jobs_restart_from_raw_deterministically() -> None:
    """Re-running a killed job from its raw inputs reproduces the same estimate."""
    inputs = {
        "fn": "numpy:multiply",
        "means": [3.0, 2.0],
        "cov": [[0.04, 0.0], [0.0, 0.01]],
        "seed": 7,
        "target": 4000,
        "batch_size": 500,
    }

    def final() -> object:
        gen = mc_steps(dict(inputs))
        try:
            next(gen)
            while True:
                gen.send(False)
        except StopIteration as stop:
            return stop.value

    assert final() == final()
