"""Shutdown with live jobs, and asyncio loop lag while acquiring at 50 kS/s with jobs active."""

# frob:ticket 01M6W7RAY4KTF866Q0Y7B4SZGG
from __future__ import annotations

import asyncio
import threading
import time
import uuid
from pathlib import Path
from uuid import uuid4

import pytest

from sadi.jobs import JobKey, JobManager, JobSpec, JobState
from sadi.logging_setup import get_logger
from sadi.store.records import NewRecord, RecordType, encode_raw_block
from sadi.store.writer_thread import Backpressure, WriterHandle

_log = get_logger("tests.concurrency.shutdown_lag")

LAG_P99_BUDGET_S = 0.050
PACKET_LEN = 612
#: One 7-packet block per 20 ms is ~350 pkt/s; at 7 samples/packet that is ~50 kS/s of ADC data.
BLOCK_PACKETS = 7
BLOCK_PERIOD_S = 0.020
RUN_S = 3.0
MC = {
    "fn": "numpy:multiply",
    "means": [3.0, 2.0],
    "cov": [[0.04, 0.0], [0.0, 0.01]],
    "target": 10**9,
    "batch_size": 500,
}


def _spec(n: int, key: str) -> JobSpec:
    """A long-running MC job spec that reports progress on every chunk."""
    return JobSpec(
        job_id=uuid4(),
        key=JobKey(key),
        data_version=1,
        task="sadi.jobs.tasks.mc:run_mc",
        inputs={**MC, "seed": n},
        progress_interval_ms=0,
    )


async def _until(pred, what: str, timeout_s: float = 60.0) -> None:  # type: ignore[no-untyped-def]
    """Yield to the loop until `pred()`; fail on timeout (the deadlock detector)."""
    deadline = time.monotonic() + timeout_s
    while not pred():
        if time.monotonic() > deadline:
            pytest.fail(f"timed out waiting for {what}")
        await asyncio.sleep(0.005)


def _pid_gone(pid: int) -> bool:
    """True once `pid` no longer exists or is a zombie."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return True
    return stat.rsplit(")", 1)[1].split()[0] == "Z"


# frob:tests python/sadi/jobs/manager.py::JobManager.shutdown
def test_shutdown_with_live_jobs_terminates_everything() -> None:
    """Shutdown with running and queued jobs ends them all and leaves no worker process."""

    async def scenario() -> None:
        progressing: set[str] = set()
        outcomes: dict[uuid.UUID, JobState] = {}
        pids: list[int] = []
        mgr = JobManager(
            3,  # slot 0 is reserved for interactive jobs: two background slots run, two queue
            sink=lambda env: progressing.add(env.key),
            on_outcome=lambda o: outcomes.__setitem__(o.job_id, o.state),
        )
        mgr.start()
        specs = [_spec(n, k) for n, k in enumerate(("a", "b", "c", "d"))]
        for s in specs:
            assert mgr.submit(s).is_ok
        await _until(lambda: len(progressing) >= 2, "two jobs running")
        pids.extend(p for p in (s.pid for s in mgr._slots) if p is not None)
        res = await asyncio.wait_for(mgr.shutdown(1.0), timeout=30.0)
        assert res.is_ok
        assert {s.job_id for s in specs} == set(outcomes)
        assert all(st.is_terminal for st in outcomes.values())
        m = mgr.metrics()
        assert (m.queued, m.running) == (0, 0)
        assert pids
        await _until(lambda: all(_pid_gone(p) for p in pids), "workers exited")

    asyncio.run(scenario())


# frob:tests python/sadi/store/writer_thread.py::WriterHandle.submit
# frob:tests python/sadi/jobs/manager.py::JobManager.submit
def test_loop_lag_p99_under_acquisition_and_jobs(tmp_path: Path) -> None:
    """With ~50 kS/s of RAW_BLOCKs and two live MC jobs, the loop's p99 lag stays under 50 ms."""
    (tmp_path / "wal").mkdir()
    opened = WriterHandle.open(tmp_path / "wal", uuid.UUID(int=0x1A6))
    writer = opened.unwrap()
    payload_packets = bytes(PACKET_LEN * BLOCK_PACKETS)
    stop = threading.Event()
    produced: list[int] = []

    def acquire() -> None:
        """Paced producer on its own thread, as the real acquisition thread would be."""
        next_t = time.monotonic()
        n = 0
        while not stop.is_set():
            n += 1
            rec = NewRecord(
                type=int(RecordType.RAW_BLOCK),
                payload=encode_raw_block(payload_packets, PACKET_LEN, n, n, n),
            )
            while True:
                res = writer.submit(rec)
                if res.is_ok:
                    produced.append(res.danger_ok)
                    break
                assert isinstance(res.danger_err, Backpressure)
            next_t += BLOCK_PERIOD_S
            stop.wait(max(0.0, next_t - time.monotonic()))

    async def scenario() -> list[float]:
        progressing: set[str] = set()
        mgr = JobManager(3, sink=lambda env: progressing.add(env.key))  # slot 0 is interactive-only
        mgr.start()
        for n, key in enumerate(("mc1", "mc2")):
            assert mgr.submit(_spec(n, key)).is_ok
        await _until(lambda: len(progressing) >= 2, "jobs progressing")
        thread = threading.Thread(target=acquire, name="sadi-conc-acq", daemon=True)
        thread.start()
        lags: list[float] = []
        end = time.monotonic() + RUN_S
        while time.monotonic() < end:
            t0 = time.monotonic()
            await asyncio.sleep(0.005)
            lags.append(max(0.0, time.monotonic() - t0 - 0.005))
        stop.set()
        thread.join(10.0)
        assert (await asyncio.wait_for(mgr.shutdown(1.0), timeout=30.0)).is_ok
        return lags

    lags = asyncio.run(scenario())
    assert produced, "acquisition produced nothing"
    assert writer.wait_durable(produced[-1], 30.0).is_ok
    assert writer.close().is_ok
    lags.sort()
    p99 = lags[min(len(lags) - 1, int(len(lags) * 0.99))]
    _log.info("loop lag: n=%d p99=%.1f ms max=%.1f ms", len(lags), p99 * 1e3, lags[-1] * 1e3)
    assert len(lags) > 100
    assert p99 < LAG_P99_BUDGET_S
