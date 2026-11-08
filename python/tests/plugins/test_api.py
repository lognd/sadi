"""Tests for the framework-independent plugin status view."""

# frob:ticket 01M6WFZF9FD9QNXP62MCETRNEA

from __future__ import annotations

from typani import Err, Ok

from sadi.plugins import PluginRegistry, PluginState
from sadi.plugins.api import (
    PluginLookupError,
    PluginStatus,
    get_plugin_status,
    list_plugin_status,
)
from sadi.plugins.builtin import builtin_source
from sadi.plugins.sources import BuiltinSource

_NEEDY: dict[str, object] = {
    "id": "needy",
    "version": "1.0.0",
    "api_version": ">=1.0,<2",
    "requires": [{"id": "absent"}],
    "contributions": {"labs": []},
}


def _registry() -> PluginRegistry:
    return PluginRegistry.discover([builtin_source(), BuiltinSource([_NEEDY, {"bogus": 1}])])


# frob:tests python/sadi/plugins/api.py::list_plugin_status
def test_lctt_listed_enabled() -> None:
    by_id = {s.id: s for s in list_plugin_status(_registry())}
    assert by_id["lctt"].state is PluginState.ENABLED
    assert by_id["lctt"].errors == []
    assert by_id["lctt"].version is not None


# frob:tests python/sadi/plugins/api.py::list_plugin_status
def test_failed_plugins_listed_with_error_text() -> None:
    by_id = {s.id: s for s in list_plugin_status(_registry())}
    needy = by_id["needy"]
    assert needy.state is PluginState.FAILED
    assert any("absent" in e for e in needy.errors)
    assert len(needy.findings) == len(needy.errors) > 0
    failed = [s for s in by_id.values() if s.version is None]
    assert failed and all(s.errors for s in failed)


# frob:tests python/sadi/plugins/api.py::get_plugin_status
def test_get_known_and_unknown() -> None:
    reg = _registry()
    got = get_plugin_status(reg, "lctt")
    assert isinstance(got, Ok) and got.value.id == "lctt"
    missing = get_plugin_status(reg, "nope")
    assert isinstance(missing, Err) and missing.error is PluginLookupError.NotFound


# frob:tests python/sadi/plugins/api.py::PluginStatus
def test_schema_exported_from_model() -> None:
    schema = PluginStatus.model_json_schema()
    assert set(schema["properties"]) == {
        "id",
        "version",
        "source",
        "state",
        "errors",
        "findings",
    }
