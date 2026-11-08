# Plugins

Status: current

Code: `python/sadi/plugins/` (model, sources, registry, state, doctor, status view),
`python/sadi/cli/plugins.py` (CLI), `python/sadi/server/routes_plugins.py` (HTTP).

A plugin is a Python package with a manifest that contributes labs now and exports,
analysis jobs and frontend panels later. The built-in LCTT lab is a plugin like any other.
Plugins are trusted, in-process code: there is no sandbox and no hot reload. What the
system does guarantee is that a broken plugin is reported as data and never takes the
core down.

## 1. Manifest

A plugin directory (or built-in package) carries `sadi_plugin.toml`:

```toml
id = "lctt"
version = "0.1.0"
api_version = ">=1.0,<2"

[contributions]
labs = ["sadi.labs.lctt.plugin:register"]

[[requires]]
id = "other-plugin"
version = ">=1,<2"
```

`PluginManifest` (pydantic, frozen, unknown keys rejected):

| Field | Type | Meaning |
|---|---|---|
| `id` | slug `^[a-z][a-z0-9_-]*$` | Unique plugin id |
| `version` | PEP 440 version | Plugin version, recorded in sessions |
| `api_version` | PEP 440 specifier range | Plugin API versions the plugin supports |
| `contributions` | `PluginContributions` | See below; defaults to empty |
| `requires` | list of `PluginRequirement(id, version)` | Other plugins needed; `version` is an optional range |

`PluginContributions` has four tuples of entrypoint references (`package.module:attr`):
`labs` is live (each ref is a `LabModule` or a callable returning one, validated with the
same rules as `LabRegistry.register`); `exports`, `jobs` and `panels` are reserved typed
fields, empty by default and not yet loaded.

`PLUGIN_API_VERSION` (currently `"1.0"`) is what this SADI offers.
`check_api_compat(manifest)` returns `Ok(None)` when the manifest range contains it, else
`Err(PluginApiVersionError.Incompatible)`. `parse_manifest(dict)` and
`load_manifest_toml(path)` return `Result[PluginManifest, PluginManifestError]` and never raise.

## 2. Sources

`PluginSource` is a protocol: `name` and `discover() -> Result[list[PluginCandidate],
PluginSourceError]`. A candidate holds a manifest or the `PluginIssue`s that kept one from
forming. Three sources ship:

1. **builtin** (`BuiltinSource`, list in `sadi.plugins.builtin.BUILTIN_PACKAGES`): first-party
   packages that ship a `sadi_plugin.toml` (today `sadi.labs.lctt`). The `sadi` launcher
   discovers this source at startup (`sadi.launcher.load_builtin_plugins`) and passes the
   resulting `PluginRegistry` and `LabRegistry` to the app, so `GET /api/labs` lists `lctt`.
   A plugin or source that fails is logged, warned on stderr and shown as failed in
   `/api/plugins`; the app still starts.
2. **entry points** (`EntryPointSource`, group `sadi.plugins`): an installed package registers
   an entry point that loads to a `PluginManifest`, a manifest mapping, or a zero-argument
   callable returning either. The older group `sadi.labs` (a zero-arg lab factory) is
   deprecated; `LabRegistry.discover()` still reads it and logs a warning.
3. **local directories** (`LocalDirSource`): plugins loaded by path, with no install. Search
   entries are, in priority order: the `SADI_PLUGIN_PATH` environment variable (an
   `os.pathsep` list; when set it wins), else the `plugin_paths` setting
   (`PluginSettings.plugin_paths`), else the defaults `plugins/` and `private/*/plugin` under
   the repository root (both gitignored; absent directories are skipped silently, so the
   public repo works without them). An entry that contains `sadi_plugin.toml` is itself a
   plugin; otherwise each child directory (not starting with `.` or `_`) is tried. The package
   is imported as `sadi_local_plugins.<id>`, so it cannot shadow core modules.

## 3. Discovery

```python
registry = PluginRegistry.discover(sources, disabled=frozenset())
```

`discover` never raises. Each candidate becomes a `PluginRecord(name, source, state,
manifest, errors, labs, loaded_at)` in deterministic order; `rec.id` is the manifest id or
the candidate name. States (`PluginState`): `enabled`, `disabled`, `failed`, `incompatible`.
Steps per candidate: manifest present, duplicate id check (first wins, later is `failed`),
API compatibility (`incompatible`), the disabled set (`disabled`, not imported), `requires`
resolution (unmet means `failed`, repeated until stable, again after import), then import
inside a guard that turns any exception into a `failed` record. A source that fails as a
whole is kept as a `PluginIssue` in `registry.source_errors()`.

Accessors: `records()`, `get(id)`, `labs()` (labs of enabled plugins), `source_errors()`.

## 4. Error sets

All are typani `ErrorSet`s whose member descriptions say what to do next; the per-plugin
unit is `PluginIssue(kind, note)`.

| Set | Members |
|---|---|
| `PluginManifestError` | `Unreadable`, `BadToml`, `MissingField`, `InvalidField` |
| `PluginApiVersionError` | `Incompatible` |
| `PluginImportError` | `ImportFailed`, `BadContribution` |
| `PluginRequiresError` | `Missing`, `VersionMismatch` |
| `PluginDuplicateIdError` | `Duplicate` |
| `PluginSourceError` | `Unavailable`, `BadCandidate` |
| `PluginStateError` | `Unreadable`, `Corrupt`, `WriteFailed` (state file, section 6) |
| `PluginLookupError` | `NotFound` (status lookup) |

## 5. The boundary rule

Plugins import only the public core API: public modules of `sadi.core`, `sadi.uncertainty`,
`sadi.logging_setup`, and their own package. They must not import `sadi.store` (WAL and
session store), private `_modules`, or another plugin. The boundary test
(`test_labs_import_only_core_public_api`, see [Lab modules](core/lab-modules.md)) enforces this
for built-in labs. The reverse also holds: nothing in core names a specific plugin.

## 6. Enable and disable state

State lives in `plugins.json` in the per-user config dir (`$XDG_CONFIG_HOME/sadi`, else
`~/.config/sadi`; `PluginSettings.config_dir`), never in session data:

```json
{"version": 1, "disabled": ["some-plugin"]}
```

Writes are atomic (temp file, fsync, rename). A missing file means nothing is disabled. A
damaged file is never overwritten: `set_enabled` renames it to `plugins.json.corrupt-<ns>` and
returns `PluginStateError.Corrupt`; reads treat it as an error and the CLI falls back to
all-enabled with a warning. Changes take effect on the next start.

## 7. CLI

```
python -m sadi.cli.plugins [--config-dir DIR] list [--json]
python -m sadi.cli.plugins info <id>
python -m sadi.cli.plugins enable <id>
python -m sadi.cli.plugins disable <id>
```

A `sadi plugins` console script is landing in ~HTA7GFF; until then use the module form.
`list` prints id, version, source and state (or JSON rows); `info` adds the API range, labs,
requirements and error notes. Exit codes (`Exit`): 0 success, 2 unknown plugin id or bad
arguments, 3 state file unreadable or unwritable. Failures print one plain line.

## 8. HTTP

`make_plugins_router(registry)` builds a read-only router: `GET /api/plugins` returns a list
of `PluginStatus` (always HTTP 200, failed plugins included) and `GET /api/plugins/{id}`
returns one or 404. `PluginStatus` is `{id, version, source, state, errors, findings}`:
`errors` are `Kind: note` strings and `findings` the guidance text per error kind. The router
exists but is not yet mounted by the app factory (~M3X7GSY).

## 9. Doctor checks

`check_plugins(registry, session_refs)` (in `sadi.plugins.doctor`) is pure and returns
`DoctorFinding(plugin_id, severity, code, message, fixes)` with numbered fix steps. See
[sadi doctor](doctor.md) section 3.16 for the code catalog.

## 10. Session provenance

Each session version's `manifest.json` may record `plugins: [{id, version}]`, the plugins
active when it was made (`SessionPluginRef`). `create`/`resume` accept the list; resume
inherits the parent's when none is given. On reopen, passing `available_plugins` (id to
version) yields `plugin_warnings`: a missing or version-changed plugin only warns, the
session still opens. Details: [Data safety 8.4.1](data-safety.md).

## 11. Writing a local plugin

1. Create `plugins/my-lab/` (or any directory on `SADI_PLUGIN_PATH`).
2. Add `sadi_plugin.toml`:

   ```toml
   id = "my-lab"
   version = "0.1.0"
   api_version = ">=1.0,<2"

   [contributions]
   labs = ["plugin:make_lab"]
   ```

3. Add `__init__.py` and `plugin.py` with `def make_lab() -> LabModule`, importing only the
   public core API (section 5). Refs are relative to your plugin package.
4. Run `python -m sadi.cli.plugins list`; the plugin should show `enabled`. If it shows
   `failed`, run `info my-lab` or `sadi doctor` for numbered fix steps.

## 12. Known gaps

- The lctt `LcttLab.recompute` is still a stub (~9T1EX41, blocked on a core contract decision).
- The `sadi plugins` console script (~HTA7GFF) and mounting `/api/plugins` (~M3X7GSY) are pending.
