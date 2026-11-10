"""Results/export/close finish the live acquisition; status exposes stop_reason and fault."""

# frob:ticket 01M724E09H9X4DDW9ATK14JQ5C
from __future__ import annotations

import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.device import DeviceService, DeviceSource
from sadi.core.pipeline import Bus
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.server.live import STOP_FINISHED, LiveAcquisition
from sadi.store.records import RecordType
from sadi.store.wal import WalReader


def _raw_count(root: Path) -> int:
    wal_dir = next((root / "sessions").iterdir()) / "wal"
    return sum(
        1
        for r in WalReader(wal_dir).records()
        if r.is_ok and RecordType(r.danger_ok.type) == RecordType.RAW_BLOCK
    )


@contextmanager
def _session(tmp_path: Path) -> Generator[tuple[TestClient, LiveAcquisition]]:
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    dev = DeviceService(DeviceSource(kind="sim", manual_load=True))
    assert dev.open().is_ok
    live = LiveAcquisition(dev, Bus(), watch_poll_s=3600.0)
    app = create_app(
        AppSettings(
            data_root=tmp_path,
            labs=labs,
            device=dev,
            bus=live.bus,
            live=live,
            synthetic=True,
            require_root_lock=False,
        )
    )
    with TestClient(app) as c:
        assert c.post("/api/sessions", json={"lab": "lctt", "slug": "s"}).status_code == 201
        try:
            yield c, live
        finally:
            c.post("/api/session/close")
    dev.close()


# frob:tests python/sadi/server/service.py::SessionService.finish_acquisition
# frob:tests python/sadi/server/service.py::SessionService.acquisition_state
def test_results_finish_stops_raw_and_reports_reason(tmp_path: Path) -> None:
    """POST /results/finish stops streaming, keeps blocks, and status shows stop_reason."""
    with _session(tmp_path) as (c, live):
        time.sleep(0.4)
        before = c.get("/api/device/status").json()
        assert before["stop_reason"] is None
        got = c.post("/api/results/finish")
        assert got.status_code == 200
        assert got.json()["stop_reason"] == STOP_FINISHED
        assert not live.running
        n = _raw_count(tmp_path)
        assert n > 0
        time.sleep(0.4)
        assert _raw_count(tmp_path) == n
        assert c.post("/api/results/finish").status_code == 200  # idempotent


# frob:tests python/sadi/server/routes/export.py::render_export
def test_export_finishes_acquisition_first(tmp_path: Path) -> None:
    """Reaching export drains and stops raw streaming before computing."""
    with _session(tmp_path) as (c, live):
        time.sleep(0.4)
        fmt = c.get("/api/export").json()[0]["id"]
        c.get(f"/api/export/{fmt}")
        assert live.stop_reason == STOP_FINISHED
        n = _raw_count(tmp_path)
        time.sleep(0.4)
        assert _raw_count(tmp_path) == n


# frob:tests python/sadi/server/routes/results.py::make_results_router
def test_status_exposes_acquisition_fault(tmp_path: Path) -> None:
    """A recorded fault is surfaced as acquisition_fault in the status response."""
    from sadi.api.acquisition import DriverFault

    with _session(tmp_path) as (c, live):
        live._fault = DriverFault(origin="disk", detail="low")  # noqa: SLF001
        body = c.get("/api/device/status").json()
        assert body["acquisition_fault"] == "disk: low"


# frob:tests python/sadi/server/service.py::SessionService.close
def test_close_keeps_wal_blocks(tmp_path: Path) -> None:
    """Closing finishes first; every raw block recorded so far stays in the WAL."""
    with _session(tmp_path) as (c, _live):
        time.sleep(0.4)
        assert c.post("/api/session/close").status_code in (200, 204)
        assert _raw_count(tmp_path) > 0
