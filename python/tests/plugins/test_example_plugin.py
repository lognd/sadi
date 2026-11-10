"""The tracked example lab plugin loads through SADI_PLUGIN_PATH and works."""

# frob:ticket 01M730K5BRST4QJ68VYQBA1KD9

from __future__ import annotations

from pathlib import Path

from typani import Err, Ok

from sadi.core.lab import LabId
from sadi.core.models import CapturedPoint, SettleStatus, TimeWindow
from sadi.core.registry import LabRegistry
from sadi.plugins import PluginRegistry, PluginState
from sadi.plugins.local import LocalDirSource

EXAMPLES = Path(__file__).resolve().parents[3] / "examples" / "plugins"


def _registry() -> PluginRegistry:
    env = {"SADI_PLUGIN_PATH": str(EXAMPLES)}
    return PluginRegistry.discover([LocalDirSource(env=env)])


def _pt(i: int, kg: float | None) -> CapturedPoint:
    return CapturedPoint(
        index=i,
        window=TimeWindow(start=0.0, end=1.0),
        t_since_load=1.0,
        drift_rate=0.0,
        status=SettleStatus.SETTLED,
        load_kg=kg,
    )


# frob:tests python/sadi/plugins/local.py::LocalDirSource.discover
def test_example_discovered_and_enabled() -> None:
    rec = _registry().get("example-lab")
    assert rec is not None
    assert rec.state == PluginState.ENABLED
    assert [lab.id for lab in rec.labs] == [LabId("example-lab")]


# frob:tests python/sadi/core/registry.py::LabRegistry.from_plugins
# frob:tests examples/plugins/example-lab/plugin.py::make_lab
# frob:tests examples/plugins/example-lab/plugin.py::ExampleLab.steps
# frob:tests examples/plugins/example-lab/plugin.py::ExampleLab.recompute
def test_example_lab_registered_and_runs() -> None:
    labs = LabRegistry.from_plugins(_registry())
    got = labs.get(LabId("example-lab"))
    assert isinstance(got, Ok)
    lab = got.value
    assert lab.title == "Example lab (plugin demo)"
    assert [s.id for s in lab.steps()] == ["measure"]
    res = lab.recompute((_pt(0, 1.0), _pt(1, 3.0)))
    assert isinstance(res, Ok)
    assert res.value.values["mean_load"].value == 2.0
    assert isinstance(lab.recompute(()), Err)


def test_example_imports_only_public_api() -> None:
    src = (EXAMPLES / "example-lab" / "plugin.py").read_text(encoding="utf-8")
    for banned in ("sadi.store", "private", "labview", "print("):
        assert banned not in src
