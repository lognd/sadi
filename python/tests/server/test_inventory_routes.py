"""Inventory routes: durable NOTE events, no deletes, 501 without a provider, resume keeps them."""

# frob:ticket 01M6WTC9ZQWCTYX5WADMDHYBZ1

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typani import Err, Ok, Result

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.app import AppSettings, create_app
from sadi.server.routes.inventory import EventKind
from sadi.server.service import SessionService


class _Stub:
    """Generic stand-in provider: events are `{kind, n, v}`; the view maps n to its history."""

    def parse(self, kind: EventKind, body: dict[str, Any]) -> Result[str, str]:
        if "n" not in body:
            return Err("n is required")
        return Ok(json.dumps({"kind": kind, **body}))

    def snapshot(self, events: Sequence[str]) -> Result[dict[str, Any], str]:
        out: dict[str, list[Any]] = {}
        for e in events:
            d = json.loads(e)
            out.setdefault(str(d["n"]), []).append(d.get("v"))
        if any(len(v) > 3 for v in out.values()):
            return Err("too many edits")
        return Ok({"entries": out})

    def combo(self, events: Sequence[str], numbers: Sequence[int]) -> Result[dict[str, Any], str]:
        if 99 in numbers:
            return Err("unknown weight 99")
        return Ok({"count": len(numbers), "events": len(events)})


def _app(root: Path, provider: _Stub | None) -> tuple[FastAPI, SessionService]:
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    app = create_app(AppSettings(data_root=root, labs=labs, inventory=provider))
    return app, cast(SessionService, app.state.sessions)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    """App with a stub provider and an open session."""
    app, _ = _app(tmp_path, _Stub())
    with TestClient(app) as c:
        assert (
            c.post("/api/sessions", json={"lab": "lctt", "slug": "t", "specimen": {}}).status_code
            == 201
        )
        yield c


# frob:tests python/sadi/server/routes/inventory.py::make_inventory_router
def test_create_edit_view_keeps_history(client: TestClient) -> None:
    a = client.post("/api/session/inventory/weights", json={"n": 1, "v": 1})
    b = client.post("/api/session/inventory/weights", json={"n": 1, "v": 2})
    assert a.status_code == b.status_code == 201
    assert b.json()["seq"] > a.json()["seq"]
    assert client.get("/api/session/inventory").json() == {"entries": {"1": [1, 2]}}


# frob:tests python/sadi/server/routes/inventory.py::make_inventory_router
# frob:tests python/sadi/server/routes/inventory.py::InventoryProvider.parse
# frob:tests python/sadi/server/routes/inventory.py::InventoryProvider.snapshot
# frob:tests python/sadi/server/routes/inventory.py::InventoryProvider.combo
def test_group_and_combo(client: TestClient) -> None:
    assert client.post("/api/session/inventory/groups", json={"n": 5, "v": 9}).status_code == 201
    res = client.post("/api/session/inventory/combo", json={"numbers": [1, 2]})
    assert res.json() == {"count": 2, "events": 1}


# frob:tests python/sadi/server/routes/inventory.py::make_inventory_router
def test_refusals_are_problem_json_with_hint(client: TestClient) -> None:
    bad = client.post("/api/session/inventory/weights", json={"v": 1})
    assert bad.status_code == 422 and bad.json()["hint"]
    assert bad.headers["content-type"].startswith("application/problem+json")
    for _ in range(4):
        last = client.post("/api/session/inventory/weights", json={"n": 2, "v": 0})
    assert last.status_code == 422
    assert client.get("/api/session/inventory").json()["entries"]["2"] == [0, 0, 0]
    assert client.post("/api/session/inventory/combo", json={"numbers": [99]}).status_code == 422
    assert client.post("/api/session/inventory/combo", json={"numbers": []}).status_code == 422


# frob:tests python/sadi/server/routes/inventory.py::make_inventory_router
def test_no_provider_is_501(tmp_path: Path) -> None:
    app, _ = _app(tmp_path, None)
    with TestClient(app) as c:
        res = c.get("/api/session/inventory")
        assert res.status_code == 501
        assert "plugin" in res.json()["hint"]


# frob:tests python/sadi/server/routes/inventory.py::make_inventory_router
def test_no_open_session_is_409(tmp_path: Path) -> None:
    app, _ = _app(tmp_path, _Stub())
    with TestClient(app) as c:
        assert c.get("/api/session/inventory").status_code == 409
        assert c.post("/api/session/inventory/weights", json={"n": 1}).status_code == 409


# frob:tests python/sadi/server/service.py::SessionService.append_note
# frob:tests python/sadi/server/service.py::SessionService.notes
# frob:tests python/sadi/server/service.py::_fold_parent
def test_events_survive_resume(client: TestClient) -> None:
    client.post("/api/session/inventory/weights", json={"n": 1, "v": 7})
    name = client.get("/api/session").json()["name"]
    assert client.post("/api/session/close").status_code == 204
    assert client.post("/api/sessions/resume", json={"name": name}).status_code == 201
    assert client.get("/api/session/inventory").json() == {"entries": {"1": [7]}}
