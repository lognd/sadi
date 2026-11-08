"""Kill the acquisition process mid-run, recover the session and continue as a new version."""

# frob:ticket 01M6W7RB61AEQRD899AWKK27QJ
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

pytest.importorskip("sadi_py", reason="native extension not built")

from sadi.logging_setup import get_logger
from sadi.store.records import RecordType
from sadi.store.session import resume_session
from sadi.store.wal import WalReader
from tests.e2e.harness import run_scenario
from tests.e2e.scenarios import BASELINE, DURATION_S, LOAD_AT_S, scenario_dict

_log = get_logger("tests.e2e.kill_resume")

KILLEE = Path(__file__).with_name("killee.py")
READY_TIMEOUT_S = 60.0


def _digest(root: Path) -> str:
    """Hash every file (relative name and bytes) under `root`."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode())
            h.update(p.read_bytes())
    return h.hexdigest()


def _spawn(root: Path, ready: Path) -> subprocess.Popen[bytes]:
    """Start the killee with `sadi` and `tests` importable."""
    env = dict(os.environ)
    pkg_root = str(Path(__file__).resolve().parents[2])
    env["PYTHONPATH"] = pkg_root + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.Popen(
        [sys.executable, str(KILLEE), str(root), str(ready)],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


# frob:tests python/sadi/store/session.py::resume_session
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.ingest
def test_sigkill_mid_run_recovers_and_continues_as_new_version(tmp_path: Path) -> None:
    """SIGKILL during acquisition: v001 stays intact and v002 continues the run."""
    root = tmp_path / "data"
    ready = tmp_path / "ready"
    proc = _spawn(root, ready)
    try:
        deadline = time.monotonic() + READY_TIMEOUT_S
        while not ready.exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), "killee never became ready"
        proc.kill()
    finally:
        proc.kill()
        proc.wait()
    v1 = Path(ready.read_text())
    _log.info("killed acquisition in %s", v1.name)

    scan = WalReader.scan(v1 / "wal")
    assert scan.is_ok, scan
    before_raw = [r.danger_ok for r in WalReader(v1 / "wal").records() if r.is_ok]
    raw_before = [r for r in before_raw if r.type == RecordType.RAW_BLOCK]
    assert len(raw_before) >= 5
    digest = _digest(v1)

    # The killed process left the data-root lock behind: plain resume refuses, recovery proceeds.
    refused = resume_session(v1)
    if refused.is_ok:
        refused.danger_ok.close()
    resumed = refused if refused.is_ok else resume_session(v1, recover_stale=True)
    assert resumed.is_ok, resumed
    handle = resumed.danger_ok
    try:
        assert handle.path.name.endswith(".v002")
        assert handle.manifest.parent == v1.name
        assert handle.manifest.parent_last_seq is not None
        assert handle.manifest.parent_last_seq >= len(raw_before)
        run = run_scenario(
            scenario_dict(BASELINE),
            handle.path / "wal",
            duration_s=DURATION_S / 2,
            load_at_s=LOAD_AT_S,
        )
        assert run.of_type(RecordType.RAW_BLOCK)
    finally:
        handle.close()

    assert _digest(v1) == digest, "resume modified the killed parent version"
