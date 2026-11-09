# SADI

Status: current

Documentation lives in [docs/index.md](docs/index.md).

## Quick start

Run everything below from `python/` of a checkout, after `uv sync --frozen`
(`cd python && uv run --frozen python ...`). SADI logs through the standard `logging`
module; the snippets below omit that output.

### Run the app

```
cd python
uv run --frozen sadi --sim            # simulator device, opens the browser
uv run --frozen sadi --sim --selftest # run one simulated acquisition and exit
```

The launcher runs the doctor preflight first. See the [user guide](docs/user-guide.md) and
[sadi doctor](docs/doctor.md).

### Use the library

Fallible calls return typani `Result` values (`Ok` / `Err`) instead of raising; match on
them. Plugins are found by a `PluginRegistry`, and a `LabRegistry` is a validated view over
the labs of the enabled plugins. The built-in `lctt` lab is a plugin like any other.

```python
from typani import Err, Ok

from sadi.core.models import Quantity
from sadi.core.registry import LabRegistry
from sadi.plugins import PluginRegistry
from sadi.plugins.builtin import builtin_source
from sadi.plugins.local import LocalDirSource

plugins = PluginRegistry.discover([builtin_source(), LocalDirSource()])  # never raises
for rec in plugins.records():
    print(rec.id, rec.state.value)  # e.g. "lctt enabled"

labs = LabRegistry.from_plugins(plugins)
match labs.get("lctt"):
    case Ok(lab):
        print(lab.title, [s.id for s in lab.steps()])
        match lab.recompute(()):  # no captured points yet
            case Ok(result):
                print(result.values)
            case Err(e):
                print("recompute failed:", e.code)  # TOO_FEW_POINTS style codes
    case Err(e):
        print("no such lab:", e.code, e.detail)  # UNKNOWN_ID

# Measured values carry a 95 % standard uncertainty and must use an SI unit symbol.
print(Quantity(value=9.81, standard_uncertainty=0.02, unit="m"))
```

Background: [architecture](docs/architecture.md), [Python layout](docs/python-layout.md),
[lab modules](docs/core/lab-modules.md), [acquisition driver](docs/api/acquisition.md).

### Make a plugin

A plugin is a directory with a `sadi_plugin.toml` manifest and a Python package that
contributes a lab. Plugins are trusted in-process code and may import only the public core
API (`sadi.core`, `sadi.uncertainty`, `sadi.logging_setup`); see
[plugins](docs/plugins.md) section 5.

1. Create `plugins/my-lab/` in the repository root (gitignored; or any directory listed in
   `SADI_PLUGIN_PATH`).
2. Add `plugins/my-lab/sadi_plugin.toml`:

   ```toml
   id = "my-lab"
   version = "0.1.0"
   api_version = ">=1.0,<2"

   [contributions]
   labs = ["plugin:make_lab"]   # module:attr, relative to the plugin package
   ```

3. Add an empty `plugins/my-lab/__init__.py` and `plugins/my-lab/plugin.py`:

   ```python
   from __future__ import annotations

   from typani import Err, Ok, Result

   from sadi.core.errors import ComputeCode, ComputeError
   from sadi.core.lab import AnalysisResult, CaptureKind, LabId, LabModule, StepId, StepSpec
   from sadi.core.models import CapturedPoint, Phase, Quantity, RunState


   def _guidance(state: RunState) -> str:
       return "Hang the load, wait for the reading to settle, then capture."


   class MyLab:
       """One capture step; the result is the mean applied load."""

       id = LabId("my-lab")
       title = "My lab"
       models = ()
       export_formats = ()

       def steps(self) -> list[StepSpec]:
           return [
               StepSpec(
                   id=StepId("measure"),
                   title="Measure",
                   phase=Phase.ELASTIC,
                   capture=CaptureKind.DEVICE_POINTS,
                   guidance=_guidance,
                   min_points=1,
               )
           ]

       def recompute(
           self, points: tuple[CapturedPoint, ...]
       ) -> Result[AnalysisResult, ComputeError]:
           loads = [p.load_kg for p in points if p.load_kg is not None]
           if not loads:
               return Err(ComputeError(code=ComputeCode.TOO_FEW_POINTS, detail="no loads"))
           mean = sum(loads) / len(loads)
           return Ok(AnalysisResult(values={"mean_load": Quantity(value=mean, unit="kg")}))


   def make_lab() -> LabModule:
       return MyLab()
   ```

4. Check it is discovered (add `SADI_PLUGIN_PATH=/path/to/dir` if it is not under
   `plugins/`; the variable names the directory that contains `my-lab/`):

   ```
   cd python
   uv run --frozen sadi-plugins list
   ```

   ```
   ID      VERSION  SOURCE     STATE
   lctt    0.1.0    builtin    enabled
   my-lab  0.1.0    local-dir  enabled
   ```

   The plugin now shows up through `LabRegistry.from_plugins(...)` (snippet above:
   `labs.get("my-lab")` is `Ok`). A broken plugin is reported as `failed` data and never
   stops the app; run `uv run --frozen sadi-plugins info my-lab` or `sadi-doctor` for fix
   steps. Installed packages can instead register an entry point in the `sadi.plugins`
   group. Full manifest, source and error reference: [plugins](docs/plugins.md); lab
   contract: [lab modules](docs/core/lab-modules.md).
