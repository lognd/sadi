"""AD3-sourced acquisition subprocess killed mid-run by test_lctt_ad3: real session, fake AD3, WAL.

Usage: python killee_ad3.py <root> <ready_file>
"""

# frob:ticket 01M6Z32CP3XANNZ4ZRNGHQ8PEY
from __future__ import annotations

import sys
import time
import uuid
from pathlib import Path

from sadi.bench.lctt_source import Ad3Source, Segment
from sadi.core.pipeline import AcquisitionPipeline, PipelineConfig
from sadi.labs.lctt.settle_stream import StreamConfig
from sadi.logging_setup import get_logger
from sadi.store.session import SessionMeta, create_session
from sadi.store.wal import WalConfig
from sadi.store.writer_thread import WriterHandle
from tests.e2e.ad3_flow import PACKET_LEN, RATE_HZ, SETTLE, TARE_V, make_fake

_log = get_logger("tests.e2e.killee_ad3")

READY_AFTER_BLOCKS = 5
MAX_RUN_S = 30.0


def main(root: Path, ready: Path) -> int:
    """Acquire AD3 blocks into a fresh session until killed; return a process exit code."""
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
        stream=StreamConfig(settle=SETTLE), sample_rate_hz=RATE_HZ, packet_len=PACKET_LEN
    )
    pipe = AcquisitionPipeline(writer, cfg)
    be = make_fake()
    dev = be.open(0).danger_ok
    src = Ad3Source(be, dev, rate_hz=RATE_HZ)
    deadline = time.monotonic() + MAX_RUN_S
    n = 0
    try:
        while time.monotonic() < deadline:
            got = src.stream([Segment(lvdt_v=TARE_V, load_v=0.1, n=1000)])
            if got.is_err or pipe.ingest(src.to_block(got.danger_ok, PACKET_LEN)).is_err:
                return 4
            n += 1
            if n == READY_AFTER_BLOCKS:
                writer.wait_durable(writer.enqueued_seq, 10.0)
                ready.write_text(str(handle.path))
                _log.info("ready after %d blocks", n)
            time.sleep(0.01)
    finally:
        be.close(dev)
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1]), Path(sys.argv[2])))
