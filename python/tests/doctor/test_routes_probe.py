"""Audit1 #10/#11: GET /api/doctor uses the server data root and never probes the port."""
# frob:ticket 01M71XGJ7JM6YWRWCPMTRQJ0A5

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from sadi.server.routes_doctor import make_doctor_router


# frob:tests python/sadi/server/routes_doctor.py::make_doctor_router
def test_list_uses_configured_data_root_and_never_probes_port(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit1 #10/#11: GET reports the --data-root and never opens a serial port."""
    import sadi.doctor.probes as probes_mod

    def boom(*_a: object, **_k: object) -> None:
        raise AssertionError("GET /api/doctor must not probe the device")

    monkeypatch.setattr(probes_mod, "probe_device", boom)
    app = FastAPI()
    app.include_router(make_doctor_router(tmp_path))
    body = TestClient(app).get("/api/doctor").json()
    assert body["host"]["data_root"] == str(tmp_path)
    dev = [r for r in body["results"] if r["id"].startswith("DEV-")]
    assert dev
    assert all(r["status"] == "skip" and r["skip_reason"] in {"read-only", "opt-in"} for r in dev)
