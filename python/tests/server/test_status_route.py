"""GET /api/status reports firmware, sample rate and the active data root."""

# frob:ticket 01M71T683VDS38T2GYYW9SXT5B

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sadi.core.device import DEVICE_RATE_HZ, DeviceService, DeviceSource
from sadi.core.pipeline import Bus
from sadi.server.app import AppSettings, create_app
from sadi.server.live import DECIMATE, LiveAcquisition
from sadi.server.routes.status import make_status_router


class _Src:
    firmware = "fw-1.2"
    sample_rate_hz = 250.0


def _client(root: Path, src: _Src | None) -> TestClient:
    app = FastAPI()
    app.include_router(make_status_router(root, src))
    return TestClient(app)


def test_status_reports_live_values(tmp_path: Path) -> None:
    """Firmware, rate and the given root are returned."""
    body = _client(tmp_path, _Src()).get("/api/status").json()
    assert body == {"firmware": "fw-1.2", "sample_rate_hz": 250.0, "data_root": str(tmp_path.resolve())}


def test_status_without_live_is_null(tmp_path: Path) -> None:
    """No live source: firmware and rate are null, root still reported."""
    body = _client(tmp_path, None).get("/api/status").json()
    assert body["firmware"] is None and body["sample_rate_hz"] is None
    assert body["data_root"] == str(tmp_path.resolve())


def test_status_mounted_in_app_uses_active_root(tmp_path: Path) -> None:
    """create_app serves the route with the --data-root it was given."""
    app = create_app(AppSettings(data_root=tmp_path, require_root_lock=False))
    assert TestClient(app).get("/api/status").json()["data_root"] == str(tmp_path.resolve())


# frob:tests python/sadi/server/live.py::LiveAcquisition.firmware
# frob:tests python/sadi/server/live.py::LiveAcquisition.sample_rate_hz
# frob:tests python/sadi/server/routes/status.py::StatusSource.firmware
# frob:tests python/sadi/server/routes/status.py::StatusSource.sample_rate_hz
def test_status_from_real_live_acquisition(tmp_path: Path) -> None:
    """A real LiveAcquisition satisfies the StatusSource port."""
    dev = DeviceService(DeviceSource(kind="sim", manual_load=True))
    assert dev.open().is_ok
    live = LiveAcquisition(dev, Bus(), watch_poll_s=3600.0)  # type: ignore[arg-type]
    app = FastAPI()
    app.include_router(make_status_router(tmp_path, live))
    body = TestClient(app).get("/api/status").json()
    assert isinstance(body["firmware"], str) and body["firmware"]
    assert body["sample_rate_hz"] == DEVICE_RATE_HZ / DECIMATE
