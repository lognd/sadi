"""Tests for the plugin doctor checks."""

# frob:ticket 01M6WFZF4QDHYXTXX797A3KGX0

from __future__ import annotations

from typing import Any

import pytest

from sadi.plugins import (
    BuiltinSource,
    PluginRecord,
    PluginRegistry,
    PluginState,
)
from sadi.plugins.doctor import check_plugins
from sadi.plugins.errors import (
    PluginImportError,
    PluginManifestError,
    PluginSourceError,
)
from sadi.plugins.sources import PluginIssue
from sadi.store.manifest import SessionPluginRef


def _mf(pid: str, **extra: Any) -> dict[str, Any]:
    return {"id": pid, "version": "1.0.0", "api_version": ">=1.0,<2", **extra}


def _codes(reg: PluginRegistry, refs: tuple[SessionPluginRef, ...] = ()) -> dict[str, list[str]]:
    return {f.code: list(f.fixes) for f in check_plugins(reg, refs)}


def _check_numbered(fixes: list[str]) -> None:
    assert len(fixes) >= 2
    for i, s in enumerate(fixes, 1):
        assert s.startswith(f"{i}. ")


# frob:tests python/sadi/plugins/doctor.py::check_plugins
def test_healthy_registry_has_no_findings() -> None:
    reg = PluginRegistry.discover([BuiltinSource([_mf("good")])])
    assert check_plugins(reg) == []


# frob:tests python/sadi/plugins/doctor.py::check_plugins
@pytest.mark.parametrize(
    ("sources", "disabled", "code"),
    [
        ([BuiltinSource([_mf("a", api_version=">=9")])], (), "plugin.api_incompatible"),
        (
            [BuiltinSource([_mf("a", requires=[{"id": "nope"}])])],
            (),
            "plugin.requires_missing",
        ),
        ([BuiltinSource([_mf("a"), _mf("a")])], (), "plugin.duplicate_id"),
        ([BuiltinSource([_mf("a")])], ("a",), "plugin.disabled"),
        ([BuiltinSource([{"id": "a"}])], (), "plugin.bad_manifest"),
        (
            [BuiltinSource([_mf("a", contributions={"labs": ["no_such_mod_xyz:f"]})])],
            (),
            "plugin.import_failed",
        ),
    ],
)
def test_each_failure_state_maps_to_numbered_fixes(
    sources: list[Any], disabled: tuple[str, ...], code: str
) -> None:
    found = _codes(PluginRegistry.discover(sources, disabled))
    assert code in found
    _check_numbered(found[code])


# frob:tests python/sadi/plugins/doctor.py::check_plugins
def test_local_dir_unreadable_and_source_error() -> None:
    rec = PluginRecord(
        name="d",
        source="local-dir",
        state=PluginState.FAILED,
        errors=(PluginIssue(kind=PluginManifestError.Unreadable, note="d: no sadi_plugin.toml"),),
    )
    reg = PluginRegistry(
        [rec], [PluginIssue(kind=PluginSourceError.Unavailable, note="entry-points: boom")]
    )
    found = _codes(reg)
    assert {"plugin.local_dir_unreadable", "plugin.source_unavailable"} <= set(found)
    for fixes in found.values():
        _check_numbered(fixes)


# frob:tests python/sadi/plugins/doctor.py::check_plugins
def test_failed_record_without_cause_and_unknown_kind_never_raise() -> None:
    bare = PluginRecord(name="x", source="s", state=PluginState.FAILED)
    odd = PluginRecord(
        name="y",
        source="s",
        state=PluginState.FAILED,
        errors=(PluginIssue(kind=PluginImportError.ImportFailed, note="x" * 2000),),
    )
    out = check_plugins(PluginRegistry([bare, odd]))
    assert len(out) == 2
    assert all(len(f.fixes) >= 2 for f in out)
    assert len(out[1].message) < 600


# frob:tests python/sadi/plugins/doctor.py::check_plugins
def test_session_refs_missing_and_version_changed() -> None:
    reg = PluginRegistry.discover([BuiltinSource([_mf("here")])])
    refs = (
        SessionPluginRef(id="gone", version="1.0.0"),
        SessionPluginRef(id="here", version="0.9.0"),
        SessionPluginRef(id="here", version="1.0.0"),
    )
    found = _codes(reg, refs)
    assert "session.plugin_missing" in found
    assert "session.plugin_version_changed" in found
    for fixes in found.values():
        _check_numbered(fixes)


def test_session_plugin_ref_is_store_manifest_model() -> None:
    """Doctor re-exports the single canonical store.manifest SessionPluginRef."""
    # frob:ticket 01M6WHAKY5X32CK3JXWC13VH4Y
    import sadi.plugins.doctor as doctor
    import sadi.store.manifest as manifest

    assert doctor.SessionPluginRef is manifest.SessionPluginRef
