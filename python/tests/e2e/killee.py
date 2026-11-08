"""Acquisition subprocess killed mid-run by test_kill_resume: real session, sim blocks, WAL.

Usage: python killee.py <root> <ready_file>

Ingests simulator batches through the pipeline into a real session WAL. Once the first
batches are durable it writes the ready file, then keeps acquiring until it is killed.
"""

# frob:ticket 01M6W7RB61AEQRD899AWKK27QJ
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

import sadi_py

from sadi.core.pipeline import AcquisitionPipeline, PipelineConfig
from sadi.labs.lctt.settle_stream import StreamConfig
from sadi.logging_setup import get_logger
from sadi.store.session import SessionMeta, create_session
from sadi.store.wal import WalConfig
from sadi.store.writer_thread import WriterHandle
from tests.e2e.harness import (
    ANALYSIS_RATE_HZ,
    BATCH_BLOCKS,
    PACKET_LEN,
    SETTLE,
    _Batch,
)
from tests.e2e.scenarios import BASELINE, scenario_dict

_log = get_logger("tests.e2e.killee")

READY_AFTER_BATCHES = 5
MAX_RUN_S = 30.0


def main(root: Path, ready: Path) -> int:
    """Acquire into a fresh session until killed; return a process exit code."""
    created = create_session(root, SessionMeta(slug="kill", lab_module="e2e"))
    if created.is_err:
        _log.error("create_session failed: %s", created.danger_err)
        return 2
    handle = created.danger_ok
    opened = WriterHandle.open(
        handle.path / "wal", uuid.UUID(handle.manifest.session_uuid), 1, WalConfig()
    )
    if opened.is_err:
        _log.error("wal open failed: %s", opened.danger_err)
        return 3
    writer = opened.danger_ok
    cfg = PipelineConfig(
        stream=StreamConfig(settle=SETTLE), sample_rate_hz=ANALYSIS_RATE_HZ, packet_len=PACKET_LEN
    )
    pipe = AcquisitionPipeline(writer, cfg)
    session, _ctl = sadi_py.sim.open(scenario_dict(BASELINE), 1)
    session.connect()
    session.start(sadi_py.AdcMode.DLL_COMPATIBLE)
    deadline = time.monotonic() + MAX_RUN_S
    n = 0
    while time.monotonic() < deadline:
        blocks = [session.read_block() for _ in range(BATCH_BLOCKS)]
        if pipe.ingest(_Batch(blocks)).is_err:
            return 4
        n += 1
        if n == READY_AFTER_BATCHES:
            writer.wait_durable(writer.enqueued_seq, 10.0)
            ready.write_text(str(handle.path))
            _log.info("ready after %d batches", n)
        time.sleep(0.01)
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
