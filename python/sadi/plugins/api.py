"""Framework-independent plugin status view: the PluginStatus model and lookups over a registry."""

# frob:ticket 01M6WFZF9FD9QNXP62MCETRNEA

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.plugins.registry import PluginRecord, PluginRegistry, PluginState

_log = get_logger(__name__)


class PluginLookupError(ErrorSet):
    """Failure modes of looking up one plugin's status."""

    NotFound = "No plugin has this id; list the plugins and use one of the ids returned"


class PluginStatus(BaseModel):
    """Read-only JSON view of one plugin: identity, state, error text and what to do next."""

    model_config = ConfigDict(frozen=True)

    id: str
    version: str | None = None
    source: str
    state: PluginState
    errors: list[str] = []
    findings: list[str] = []


def _status(rec: PluginRecord) -> PluginStatus:
    """Project a PluginRecord to its PluginStatus (error notes plus per-error guidance)."""
    return PluginStatus(
        id=rec.id,
        version=rec.manifest.version if rec.manifest else None,
        source=rec.source,
        state=rec.state,
        errors=[f"{i.kind.name}: {i.note}" if i.note else i.kind.name for i in rec.errors],
        findings=[i.kind.description for i in rec.errors],
    )


def list_plugin_status(registry: PluginRegistry) -> list[PluginStatus]:
    """Return the status of every plugin in registry order; failed plugins are included."""
    out = [_status(r) for r in registry.records()]
    _log.debug("plugin status listed: %d plugins", len(out))
    return out


def get_plugin_status(
    registry: PluginRegistry, plugin_id: str
) -> Result[PluginStatus, PluginLookupError]:
    """Return one plugin's status, or PluginLookupError.NotFound."""
    rec = registry.get(plugin_id)
    if rec is None:
        _log.info("plugin status: %r not found", plugin_id)
        return Err(PluginLookupError.NotFound)
    return Ok(_status(rec))
