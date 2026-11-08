"""Tests for sadi.plugins sources and PluginRegistry."""

# frob:ticket 01M6WFYN8C6YH5D79CPEKSP69P

from __future__ import annotations

import sys
import types
from typing import Any, cast

import pytest
from typani import Err, Ok

from sadi.core.lab import LabId
from sadi.core.registry import LabRegistry
from sadi.plugins import (
    BuiltinSource,
    EntryPointSource,
    PluginDuplicateIdError,
    PluginImportError,
    PluginRegistry,
    PluginRequiresError,
    PluginSource,
    PluginSourceError,
    PluginState,
)
from tests.core.test_lab_registry import FakeLab


def _mf(pid: str, labs: tuple[str, ...] = (), **extra: Any) -> dict[str, Any]:
    return {
        "id": pid,
        "version": "1.0.0",
        "api_version": ">=1.0,<2",
        "contributions": {"labs": list(labs)},
        **extra,
    }


@pytest.fixture(autouse=True)
def fake_module(monkeypatch: pytest.MonkeyPatch) -> None:
    """Install a throwaway module offering good and bad lab factories."""
    mod = types.ModuleType("fake_plugin_mod")

    def boom() -> Any:
        raise RuntimeError("boom")

    vars(mod).update(good=lambda: FakeLab("good-lab"), boom=boom, notalab=lambda: object())
    monkeypatch.setitem(sys.modules, "fake_plugin_mod", mod)


def _states(reg: PluginRegistry) -> dict[str, PluginState]:
    return {r.id: r.state for r in reg.records()}


# frob:tests python/sadi/plugins/registry.py::PluginRegistry.discover
# frob:tests python/sadi/plugins/sources.py::BuiltinSource.discover
def test_broken_plugin_isolated() -> None:
    src = BuiltinSource(
        [
            _mf("bad", ("fake_plugin_mod:boom",)),
            _mf("ok", ("fake_plugin_mod:good",)),
            _mf("nolab", ("fake_plugin_mod:notalab",)),
            _mf("nomod", ("no_such_mod_xyz:f",)),
        ]
    )
    reg = PluginRegistry.discover([src])
    assert _states(reg) == {
        "bad": PluginState.FAILED,
        "ok": PluginState.ENABLED,
        "nolab": PluginState.FAILED,
        "nomod": PluginState.FAILED,
    }
    bad = reg.get("bad")
    assert bad is not None and bad.errors[0].kind is PluginImportError.ImportFailed
    nolab = reg.get("nolab")
    assert nolab is not None and nolab.errors[0].kind is PluginImportError.BadContribution
    assert [lab.id for lab in reg.labs()] == [LabId("good-lab")]


def test_duplicate_and_requires_distinct() -> None:
    src = BuiltinSource(
        [
            _mf("a"),
            _mf("a"),
            _mf("b", requires=[{"id": "ghost"}]),
            _mf("c", requires=[{"id": "a", "version": ">=2"}]),
            _mf("d", requires=[{"id": "a", "version": ">=1"}]),
        ]
    )
    reg = PluginRegistry.discover([src])
    kinds = [(r.id, r.errors[0].kind if r.errors else None) for r in reg.records()]
    assert kinds == [
        ("a", None),
        ("a", PluginDuplicateIdError.Duplicate),
        ("b", PluginRequiresError.Missing),
        ("c", PluginRequiresError.VersionMismatch),
        ("d", None),
    ]


def test_disabled_recorded_not_imported() -> None:
    src = BuiltinSource([_mf("x", ("no_such_mod_xyz:f",)), _mf("y", requires=[{"id": "x"}])])
    reg = PluginRegistry.discover([src], disabled={"x"})
    assert _states(reg) == {"x": PluginState.DISABLED, "y": PluginState.FAILED}
    x = reg.get("x")
    assert x is not None and x.errors == () and x.loaded_at is None


def test_incompatible_and_bad_manifest() -> None:
    bad = _mf("old")
    bad["api_version"] = ">=9"
    reg = PluginRegistry.discover([BuiltinSource(cast("Any", [bad, {"id": "nover"}, 42]))])
    states = [r.state for r in reg.records()]
    assert states == [PluginState.INCOMPATIBLE, PluginState.FAILED, PluginState.FAILED]


def test_dependency_import_failure_propagates() -> None:
    src = BuiltinSource(
        [_mf("base", ("fake_plugin_mod:boom",)), _mf("top", requires=[{"id": "base"}])]
    )
    reg = PluginRegistry.discover([src])
    assert _states(reg) == {"base": PluginState.FAILED, "top": PluginState.FAILED}


class _EP:
    def __init__(self, name: str, obj: Any) -> None:
        self.name = name
        self._obj = obj

    def load(self) -> Any:
        if isinstance(self._obj, Exception):
            raise self._obj
        return self._obj


# frob:tests python/sadi/plugins/sources.py::EntryPointSource.discover
def test_entry_point_source() -> None:
    eps = [
        _EP("z", lambda: _mf("zed")),
        _EP("a", _mf("aye")),
        _EP("broken", ImportError("nope")),
    ]
    res = EntryPointSource(lister=lambda group: eps).discover()
    assert isinstance(res, Ok)
    assert [c.name for c in res.value] == ["aye", "broken", "zed"]
    assert res.value[1].issues[0].kind is PluginSourceError.BadCandidate
    reg = PluginRegistry.discover([EntryPointSource(lister=lambda group: eps)])
    assert _states(reg)["aye"] is PluginState.ENABLED


def test_source_failure_is_value() -> None:
    def lister(group: str) -> Any:
        raise OSError("no metadata")

    res = EntryPointSource(lister=lister).discover()
    assert isinstance(res, Err) and res.error is PluginSourceError.Unavailable

    class Exploding:
        name = "exploding"

        def discover(self) -> Any:
            raise RuntimeError("x")

    reg = PluginRegistry.discover([Exploding(), EntryPointSource(lister=lister)])  # type: ignore[list-item]
    assert reg.records() == []
    assert [i.kind for i in reg.source_errors()] == [PluginSourceError.Unavailable] * 2


# frob:tests python/sadi/core/registry.py::LabRegistry.from_plugins
# frob:tests python/sadi/core/registry.py::LabRegistry.add_plugins
def test_lab_registry_view() -> None:
    plugins = PluginRegistry.discover([BuiltinSource([_mf("ok", ("fake_plugin_mod:good",))])])
    assert LabRegistry.from_plugins(plugins).ids() == [LabId("good-lab")]


# frob:tests python/sadi/plugins/registry.py::PluginRecord.id
# frob:tests python/sadi/plugins/registry.py::PluginRegistry.__init__
# frob:tests python/sadi/plugins/registry.py::PluginRegistry.records
# frob:tests python/sadi/plugins/registry.py::PluginRegistry.get
# frob:tests python/sadi/plugins/sources.py::PluginSource.discover
# frob:tests python/sadi/plugins/sources.py::BuiltinSource.__init__
# frob:tests python/sadi/plugins/sources.py::EntryPointSource.__init__
def test_registry_accessors_and_manifestless_id() -> None:
    empty = PluginRegistry()
    assert empty.records() == [] and empty.get("x") is None
    reg = PluginRegistry.discover([BuiltinSource([{"id": "nover"}, _mf("ok")])])
    assert reg.get("nover") is not None and reg.get("ok") is not None
    assert isinstance(BuiltinSource([]), PluginSource)
    assert isinstance(EntryPointSource(), PluginSource)
