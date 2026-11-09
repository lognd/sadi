"""Wizard actions stay fast when the WAL holds a simulator-sized pile of raw records."""

# frob:ticket 01M6X3AVGVT23M1E9V82RWJ137
from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from fastapi.testclient import TestClient

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.server.service import SessionService
from sadi.store.events import recover_state
from sadi.store.records import NewRecord, RecordType, encode_raw_block
from sadi.store.writer_thread import Backpressure

WINDOW = {"first_raw_seq": 1, "last_raw_seq": 5}
RAW_RECORDS = 200_000
ACTIONS = 20
#: Generous: the old double full replay took many seconds per action at this size.
AFTER_FIRST_BOUND_S = 1.0


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the lctt lab over a tmp data root."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        yield c


# frob:tests python/sadi/server/service.py::SessionService._act
# frob:tests python/sadi/server/service.py::SessionService._replay
def test_actions_do_not_scale_with_raw_record_count(client: TestClient, tmp_path: Path) -> None:
    """200k raw records in the WAL, then 20 captures: each after the first is fast and correct."""
    assert client.post("/api/sessions", json={"lab": "lctt", "slug": "lat"}).status_code == 201
    svc = cast(SessionService, client.app.state.sessions)  # type: ignore[union-attr]
    writer = svc._open.writer  # ty: ignore[unresolved-attribute]
    raw = NewRecord(
        type=int(RecordType.RAW_BLOCK), payload=encode_raw_block(b"\x01" * 64, 8, 1, 2, 0)
    )
    last = 0
    for _ in range(RAW_RECORDS):
        sub = writer.submit(raw)
        while sub.is_err:  # slow disks (Windows fsync) fill the queue: drain, then retry
            assert isinstance(sub.danger_err, Backpressure), sub
            assert writer.wait_durable(last, 120.0).is_ok
            sub = writer.submit(raw)
        last = sub.danger_ok
    assert writer.wait_durable(last, 120.0).is_ok

    assert client.post("/api/session/wizard/skip", json={"step": "setup"}).status_code == 200
    body = {"phase": "calibration", "inputs": {"volts": 1.0, "height": 0.01}, "window": WINDOW}
    times: list[float] = []
    for _ in range(ACTIONS):
        t0 = time.monotonic()
        assert client.post("/api/session/points", json=body).status_code == 201
        times.append(time.monotonic() - t0)
    assert max(times[1:]) < AFTER_FIRST_BOUND_S, times
    assert len(client.get("/api/session/points").json()) == ACTIONS

    client.post("/api/session/close")
    (sdir,) = (tmp_path / "sessions").iterdir()
    assert len(recover_state(sdir).danger_ok.points) == ACTIONS
