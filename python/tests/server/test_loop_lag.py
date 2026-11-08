"""Loop-lag test: handlers keep answering while a blocking job occupies a worker thread."""

# frob:ticket 01M6WTCA815WPY0DGJN7DKNM2S
from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path

import httpx
import pytest
from typani import Err

from sadi.doctor.schema import DoctorError
from sadi.logging_setup import get_logger
from sadi.plugins import PluginRegistry
from sadi.plugins.builtin import builtin_source
from sadi.server import routes_doctor
from sadi.server.app import AppSettings, create_app

_log = get_logger(__name__)

# Generous: the job is held open until the probes finish, so only a blocked loop can exceed it.
_BUDGET_S = 5.0
_PROBES = 5


async def _scenario(release: threading.Event, started: threading.Event) -> list[float]:
    """Start a job that blocks on `release`, probe the API meanwhile, return probe latencies."""
    reg = PluginRegistry.discover([builtin_source()])
    app = create_app(AppSettings(registry=reg, data_root=Path("x")))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        job = asyncio.create_task(client.get("/api/doctor"))
        # Wait for the job to actually occupy a worker thread (without blocking the loop).
        while not started.is_set():
            await asyncio.sleep(0.01)
        latencies: list[float] = []
        for _ in range(_PROBES):
            t0 = time.perf_counter()
            res = await asyncio.wait_for(client.get("/api/plugins"), timeout=_BUDGET_S)
            latencies.append(time.perf_counter() - t0)
            assert res.status_code == 200
        assert not job.done(), "job finished early; probes did not overlap it"
        release.set()
        await asyncio.wait_for(job, timeout=_BUDGET_S)
    return latencies


# frob:tests python/sadi/server/routes_doctor.py::make_doctor_router
def test_handlers_respond_while_job_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fast handlers answer within budget while a blocking doctor job holds a worker thread."""
    release = threading.Event()
    started = threading.Event()

    def blocking_run(*_a: object, **_k: object) -> Err[object, DoctorError]:
        """Stand-in for a CPU-heavy job: blocks its thread until released."""
        started.set()
        assert release.wait(timeout=30)
        return Err[object, DoctorError](DoctorError.UnknownCheck)

    monkeypatch.setattr(routes_doctor, "run", blocking_run)
    latencies = asyncio.run(_scenario(release, started))
    _log.info("probe latencies: %s", latencies)
    assert max(latencies) < _BUDGET_S
