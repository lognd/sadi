"""REST routes for the weight inventory; thin handlers over an injected provider port.

The inventory model itself is supplied by a plugin (it is not part of the tracked tree), so
this module only knows the `InventoryProvider` port. Inventory events live in the session WAL
as NOTE records, written through `SessionService` (durable before the response); an edit is a
later event and nothing is ever deleted.
"""

# frob:ticket 01M6WTC9ZQWCTYX5WADMDHYBZ1
# frob:ticket 01M6WTSF7KQ3YMJP9C0Z75HVRK

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any, Literal, Protocol, runtime_checkable

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger
from sadi.server.routes.problem import ApiProblem, unwrap
from sadi.server.service import SessionService

_log = get_logger(__name__)

#: Tag marking a NOTE payload as an inventory event.
NOTE_KIND = "inventory"

EventKind = Literal["weight", "group"]


@runtime_checkable
class InventoryProvider(Protocol):
    """Port a plugin implements to validate inventory events and derive views from them."""

    def parse(self, kind: EventKind, body: dict[str, Any]) -> Result[str, str]:
        """Validate one entry and return its canonical event JSON, or a user-facing error."""
        ...

    def snapshot(self, events: Sequence[str]) -> Result[dict[str, Any], str]:
        """Fold `events` (oldest first) into the current inventory view."""
        ...

    def combo(self, events: Sequence[str], numbers: Sequence[int]) -> Result[dict[str, Any], str]:
        """Derive the combined value of the weights `numbers` from `events`."""
        ...


class EntryBody(BaseModel):
    """A weight or group entry; its fields are validated by the provider, not here."""

    model_config = ConfigDict(extra="allow")


class ComboBody(BaseModel):
    """The weight numbers to combine."""

    model_config = ConfigDict(frozen=True)
    numbers: list[int] = Field(min_length=1)


class InventoryCommitted(BaseModel):
    """Result of a durable inventory write: its WAL seq and the resulting view."""

    model_config = ConfigDict(frozen=True)
    seq: int
    inventory: dict[str, Any]


def _no_provider() -> ApiProblem:
    """The 501 problem when no plugin provides an inventory."""
    return ApiProblem(
        type="urn:sadi:error:state:no_inventory_provider",
        title="no inventory provider",
        status=501,
        detail="no plugin provides a weight inventory",
        hint="Enable a plugin that provides a weight inventory, then retry.",
    )


def _invalid(detail: str) -> ApiProblem:
    """A 422 problem for an entry or request the provider refused."""
    return ApiProblem(
        type="urn:sadi:error:input:inventory_invalid",
        title="inventory invalid",
        status=422,
        detail=detail,
        hint="Correct the entry (numbers, masses and uncertainties) and send it again.",
    )


def _wrap(event: str) -> str:
    """Tag the canonical event JSON as an inventory NOTE payload."""
    return json.dumps({"kind": NOTE_KIND, "event": json.loads(event)}, separators=(",", ":"))


def _events(svc: SessionService) -> Result[list[str], ApiProblem]:
    """Collect the inventory event JSONs of the open session, skipping unrelated notes."""
    notes = svc.notes()
    if notes.is_err:
        return Err(notes.danger_err)
    out: list[str] = []
    for text in notes.danger_ok:
        try:
            obj = json.loads(text)
        except ValueError:
            _log.debug("skipping non-JSON note")
            continue
        if isinstance(obj, dict) and obj.get("kind") == NOTE_KIND:
            out.append(json.dumps(obj["event"], separators=(",", ":")))
    return Ok(out)


def _view(svc: SessionService, provider: InventoryProvider) -> Result[dict[str, Any], ApiProblem]:
    """Current inventory view of the open session."""
    ev = _events(svc)
    if ev.is_err:
        return Err(ev.danger_err)
    snap = provider.snapshot(ev.danger_ok)
    if snap.is_err:
        return Err(_invalid(snap.danger_err))
    return Ok(snap.danger_ok)


def _record(
    svc: SessionService, provider: InventoryProvider, kind: EventKind, body: EntryBody
) -> Result[InventoryCommitted, ApiProblem]:
    """Validate an entry, append it durably, then return the new view."""
    parsed = provider.parse(kind, body.model_dump())
    if parsed.is_err:
        _log.warning("inventory %s entry refused: %s", kind, parsed.danger_err)
        return Err(_invalid(parsed.danger_err))
    prior = _events(svc)
    if prior.is_err:
        return Err(prior.danger_err)
    trial = provider.snapshot([*prior.danger_ok, parsed.danger_ok])
    if trial.is_err:
        _log.warning("inventory %s entry inconsistent: %s", kind, trial.danger_err)
        return Err(_invalid(trial.danger_err))
    seq = svc.append_note(_wrap(parsed.danger_ok))
    if seq.is_err:
        return Err(seq.danger_err)
    _log.info("inventory %s entry committed at seq %d", kind, seq.danger_ok)
    return Ok(InventoryCommitted(seq=seq.danger_ok, inventory=trial.danger_ok))


def make_inventory_router(svc: SessionService, provider: InventoryProvider | None) -> APIRouter:
    """Build the inventory router; every route answers 501 problem+json when `provider` is None."""
    r = APIRouter(prefix="/api/session/inventory")

    @r.get("")
    def view() -> dict[str, Any]:
        """Current inventory: weights with history, groups and reconciliation."""
        if provider is None:
            return unwrap(Err(_no_provider()))
        return unwrap(_view(svc, provider))

    @r.post("/weights", status_code=201)
    def put_weight(body: EntryBody) -> InventoryCommitted:
        """Add or edit a numbered weight (an edit is a later event; history is kept)."""
        if provider is None:
            return unwrap(Err(_no_provider()))
        return unwrap(_record(svc, provider, "weight", body))

    @r.post("/groups", status_code=201)
    def put_group(body: EntryBody) -> InventoryCommitted:
        """Record a group balance weighing of a named subset of weights."""
        if provider is None:
            return unwrap(Err(_no_provider()))
        return unwrap(_record(svc, provider, "group", body))

    @r.post("/combo")
    def combo(body: ComboBody) -> dict[str, Any]:
        """Derive the combined value of a subset of weights (read-only)."""
        if provider is None:
            return unwrap(Err(_no_provider()))
        ev = _events(svc)
        if ev.is_err:
            return unwrap(Err(ev.danger_err))
        got = provider.combo(ev.danger_ok, body.numbers)
        if got.is_err:
            return unwrap(Err(_invalid(got.danger_err)))
        return got.danger_ok

    return r
