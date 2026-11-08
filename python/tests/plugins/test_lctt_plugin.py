"""lctt is a built-in plugin discovered through the generic path."""

# frob:ticket 01M6WFZ1N70HDJJRZWRHWP4E7Y

from __future__ import annotations

from pathlib import Path

from typani import Ok

from sadi.core.lab import LabId
from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.plugins import PluginRegistry, PluginState
from sadi.plugins.builtin import builtin_manifests, builtin_source


# frob:tests python/sadi/plugins/builtin.py::builtin_source
def test_lctt_enabled_builtin() -> None:
    reg = PluginRegistry.discover([builtin_source()])
    rec = next(r for r in reg.records() if r.id == "lctt")
    assert rec.state is PluginState.ENABLED
    assert rec.source == "builtin"
    assert [lab.id for lab in rec.labs] == [LabId("lctt")]


# frob:tests python/sadi/plugins/builtin.py::builtin_manifests
def test_legacy_lab_registry_lookup() -> None:
    assert [m.id for m in builtin_manifests()] == ["lctt"]
    labs = LabRegistry.from_plugins(PluginRegistry.discover([builtin_source()]))
    assert isinstance(labs.get(LabId("lctt")), Ok)


def test_loader_and_registry_do_not_mention_lctt() -> None:
    base = Path(__file__).resolve().parents[2] / "sadi"
    for rel in ("plugins/registry.py", "plugins/sources.py", "core/registry.py"):
        assert "lctt" not in (base / rel).read_text(encoding="utf-8").lower()


# frob:tests python/sadi/labs/lctt/plugin.py::register
# frob:tests python/sadi/labs/lctt/plugin.py::LcttLab.steps
# frob:tests python/sadi/labs/lctt/plugin.py::LcttLab.recompute
def test_register_yields_working_lab() -> None:
    lab = register()
    assert [s.id for s in lab.steps()] == ["calibrate", "elastic", "plastic"]
    assert isinstance(lab.recompute(()), Ok)
