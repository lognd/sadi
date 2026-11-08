"""Curve and notes stay fast and correct with a simulator-sized pile of raw records."""

# frob:ticket 01M6X465ZVYG4B9Y79QAZ8KDXT
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
from sadi.server.curve_source import SessionReplayCache, make_curve_source, session_events
from sadi.server.service import SessionService
from sadi.store.records import NewRecord, RecordType, encode_raw_block

RAW_RECORDS = 200_000
CALLS = 20
BOUND_S = 1.0


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with the lctt lab over a tmp data root."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    with TestClient(create_app(AppSettings(data_root=tmp_path, labs=labs))) as c:
        yield c


# frob:ticket 01M6X9SWXACR2GWBFWEX17ZGK5
# frob:tests python/sadi/server/service.py::SessionService.notes
# frob:tests python/sadi/server/curve_source.py::make_curve_source
def test_notes_and_curve_do_not_scale_with_raw_records(client: TestClient, tmp_path: Path) -> None:
    """200k raw records, then repeated notes()/curve calls: all after the first are fast."""
    assert client.post("/api/sessions", json={"lab": "lctt", "slug": "lat"}).status_code == 201
    svc = cast(SessionService, client.app.state.sessions)  # type: ignore[union-attr]
    writer = svc._open.writer  # ty: ignore[unresolved-attribute]
    raw = NewRecord(
        type=int(RecordType.RAW_BLOCK), payload=encode_raw_block(b"\x01" * 64, 8, 1, 2, 0)
    )
    last = 0
    for _ in range(RAW_RECORDS):
        last = writer.submit(raw).danger_ok
    assert writer.wait_durable(last, 120.0).is_ok

    # Disable the periodic full re-verify so a rebuild cannot land inside the timing loop.
    source = make_curve_source(tmp_path, SessionReplayCache(reverify_interval_s=float("inf")))
    assert svc.notes().danger_ok == []
    source()
    times: list[float] = []
    for i in range(CALLS):
        assert svc.append_note(f'{{"i":{i}}}').is_ok
        t0 = time.monotonic()
        got = svc.notes()
        source()
        times.append(time.monotonic() - t0)
        assert len(got.danger_ok) == i + 1
    assert max(times) < BOUND_S, times
    (sdir,) = (tmp_path / "sessions").iterdir()
    assert session_events(sdir).is_ok
