"""Whole-app stand-in killed mid-write: a durable WAL writer plus real MC/GP worker processes.

Usage: python jobs_crashee.py <root> <oracle> <seed> <mode> <max_records>

mode `external`: the harness SIGKILLs this process once the oracle shows jobs progressing and
fresh acks. mode `self`: after the first job progress this process arms the `wal.write.partial`
failpoint so it dies between the two halves of a batch write while the workers run.
Oracle lines (single os.write each, outside the session root): the crash harness vocabulary
(`started`, `ack N`) plus `worker_pid P`, `jobs_progressing`.
"""

# frob:ticket 01M6W7RAY4KTF866Q0Y7B4SZGG
from __future__ import annotations

import asyncio
import sys
import threading
import uuid
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crash"))
import crashee  # noqa: E402  # ty: ignore[import-not-found]

from sadi.jobs import JobKey  # noqa: E402
from sadi.jobs.manager import JobManager  # noqa: E402
from sadi.jobs.pool import WorkerSlot  # noqa: E402
from sadi.jobs.state import JobSpec, ResultEnvelope  # noqa: E402
from sadi.logging_setup import get_logger  # noqa: E402
from sadi.store import failpoints  # noqa: E402
from sadi.store.records import RecordType, SessionStartV1, json_record  # noqa: E402
from sadi.store.session import SessionMeta, create_session  # noqa: E402
from sadi.store.wal import WalConfig, WalWriter  # noqa: E402

_log = get_logger("jobs_crashee")

SEG_BYTES = 1 << 20
#: Endless-enough jobs: they must still be running when the kill lands.
MC_INPUTS: dict[str, object] = {
    "fn": "numpy:multiply",
    "means": [3.0, 2.0],
    "cov": [[0.04, 0.0], [0.0, 0.01]],
    "seed": 7,
    "target": 10**9,
    "batch_size": 500,
}
GP_INPUTS: dict[str, object] = {
    "x": [[0.0], [0.4], [1.0], [2.0]],
    "y": [0.0, 0.38, 0.84, 0.91],
    "candidates": [[0.2], [0.7], [1.5], [4.0]],
}


def _writer_loop(
    writer: WalWriter, oracle: crashee.Oracle, seed: int, max_records: int,
    progressing: threading.Event, mode: str,
) -> None:  # fmt: skip
    """Append batches forever (until `max_records`), acknowledging each in the oracle."""
    rng_index = 1
    armed = False
    while rng_index < max_records:
        if progressing.is_set() and not armed:
            armed = True
            if mode == "self":
                failpoints.configure({"wal.write.partial": "once:kill"})
        n = 1 + rng_index % 4
        recs = [crashee._make_record(seed, rng_index + 1 + i) for i in range(n)]
        rng_index += n
        res = writer.append_batch(recs)
        if res.is_err:
            _log.error("append failed: %s", res.danger_err)
            return
        oracle.line(f"ack {res.danger_ok}")


async def _run_jobs(oracle: crashee.Oracle, progressing: threading.Event) -> None:
    """Start the pool, submit one MC and one GP-shaped job, report pids and first progress."""
    loop = asyncio.get_running_loop()
    slots: list[WorkerSlot] = []

    def spawn(index: int, on_event, on_death, post) -> WorkerSlot:  # type: ignore[no-untyped-def]
        slot = WorkerSlot(index, on_event, on_death, post)
        slots.append(slot)
        oracle.line(f"worker_pid {slot.pid}")
        return slot

    def sink(env: ResultEnvelope) -> None:
        if not progressing.is_set():
            progressing.set()
            oracle.line("jobs_progressing")

    mgr = JobManager(2, loop=loop, sink=sink, spawn=spawn)
    mgr.start()
    for key, task, inputs in (
        ("mc", "sadi.jobs.tasks.mc:run_mc", MC_INPUTS),
        ("gp", "sadi.jobs.tasks.gp:run_gp", GP_INPUTS),
    ):
        spec = JobSpec(
            job_id=uuid4(), key=JobKey(key), data_version=1, task=task,
            inputs=inputs, progress_interval_ms=0,
        )  # fmt: skip
        mgr.submit(spec).unwrap()
    while True:
        await asyncio.sleep(3600)


def main(argv: list[str]) -> int:
    """Create a session and WAL, start jobs, write until killed; return an exit code."""
    root, oracle_path = Path(argv[1]), Path(argv[2])
    seed, mode, max_records = int(argv[3]), argv[4], int(argv[5])
    oracle = crashee.Oracle(oracle_path)
    created = create_session(root, SessionMeta(slug="conc", lab_module="sadi.conc"))
    if created.is_err:
        return 2
    handle = created.danger_ok
    oracle.line(f"started {handle.path}")
    sid = uuid.UUID(handle.manifest.session_uuid)
    opened = WalWriter.open(handle.path / "wal", sid, 1, WalConfig(segment_max_bytes=SEG_BYTES))
    if opened.is_err:
        return 2
    writer = opened.danger_ok
    first = writer.append(
        json_record(RecordType.SESSION_START, SessionStartV1(session_uuid=str(sid)))
    )
    if first.is_err:
        return 3
    oracle.line("ack 1")
    progressing = threading.Event()
    t = threading.Thread(
        target=_writer_loop,
        args=(writer, oracle, seed, max_records, progressing, mode),
        name="sadi-conc-writer",
        daemon=True,
    )
    t.start()
    asyncio.run(_run_jobs(oracle, progressing))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
