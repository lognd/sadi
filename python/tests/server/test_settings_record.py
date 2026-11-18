"""A fresh live session WAL starts with SETTINGS before any RAW_BLOCK (audit2 H7)."""

# frob:ticket 01M723P2Z9GC152RE82Y6JYAW5
from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from sadi.core.device import DeviceService, DeviceSource
from sadi.core.pipeline import Bus
from sadi.core.registry import LabRegistry
from sadi.doctor.sessions import _raw_before_settings
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.server.live import LiveAcquisition
from sadi.store.records import RecordType, SettingsV1
from sadi.store.wal import WalReader


def _types(wal_dir: Path) -> list[RecordType]:
    return [RecordType(r.danger_ok.type) for r in WalReader(wal_dir).records() if r.is_ok]


# frob:tests python/sadi/server/live.py::LiveAcquisition.on_session_open
# frob:tests python/sadi/core/pipeline.py::AcquisitionPipeline.record_settings
def test_fresh_session_wal_has_settings_before_raw(tmp_path: Path) -> None:
    """The first RAW_BLOCK follows a SETTINGS record, so Doctor WAL-040 logic passes."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    dev = DeviceService(DeviceSource(kind="sim", manual_load=True))
    assert dev.open().is_ok
    live = LiveAcquisition(dev, Bus())
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
        made = c.post("/api/sessions", json={"lab": "lctt", "slug": "s"})
        assert made.status_code == 201
        time.sleep(1.0)
        c.post("/api/session/close")
    dev.close()
    wal_dir = next((tmp_path / "sessions").iterdir()) / "wal"
    types = _types(wal_dir)
    assert RecordType.RAW_BLOCK in types
    assert types.index(RecordType.SETTINGS) < types.index(RecordType.RAW_BLOCK)
    assert not _raw_before_settings(wal_dir)
    keys = set()
    for r in WalReader(wal_dir).records():
        if r.is_ok and r.danger_ok.type == RecordType.SETTINGS:
            s = SettingsV1.model_validate_json(r.danger_ok.payload)
            keys.add(f"{s.scope}/{s.key}")
    assert {"device/adc_full_scale_v", "acquisition/decimation", "device/kind"} <= keys

