"""GET export is read-only on acquisition; the capture gate refuses once streaming stopped."""

# frob:ticket 01M726PZGCETGKVPMAY3FJKRV6
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
from sadi.server.live import STOP_FINISHED, STOP_IDLE, LiveAcquisition


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


# frob:tests python/sadi/server/routes/export.py::render_export
def test_failed_export_mid_run_keeps_recording(tmp_path: Path) -> None:
    """A GET export (even a failing one) neither stops streaming nor blocks a load change."""
    with _session(tmp_path) as (c, live):
        assert c.post("/api/session/load-change").status_code == 200
        time.sleep(0.2)
        fmt = c.get("/api/export").json()[0]["id"]
        got = c.get(f"/api/export/{fmt}")
        assert got.status_code in (200, 422)
        assert c.get("/api/export/no-such-format").status_code >= 400
        assert live.stop_reason is None
        assert live.running
        assert c.post("/api/session/load-change").status_code == 200


# frob:tests python/sadi/server/live.py::LiveAcquisition.capture_block_hint
def test_capture_gate_refuses_when_stopped(tmp_path: Path) -> None:
    """Capture is refused with a plain hint once finished or idle, and allowed while running."""
    with _session(tmp_path) as (_c, live):
        assert live.capture_block_hint() is None
        live._stop_reason = STOP_IDLE  # noqa: SLF001
        assert "idle" in (live.capture_block_hint() or "")
        assert c_post_finish(_c) == STOP_FINISHED
        assert "finished" in (live.capture_block_hint() or "")


def c_post_finish(c: TestClient) -> str | None:
    """POST /results/finish and return the reported stop_reason."""
    got = c.post("/api/results/finish")
    assert got.status_code == 200
    return got.json()["stop_reason"]
