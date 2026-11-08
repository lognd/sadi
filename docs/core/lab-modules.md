# Lab modules

Status: current

Owner: ~CYC6ZT7. Code: `python/sadi/core/lab.py`, `python/sadi/core/registry.py`.
Tests: `python/tests/core/test_lab_registry.py`.

A lab is one kind of contribution of a [plugin](../plugins.md) (manifest key
`contributions.labs`). There is no sandboxing and no hot reload: labs are trusted, in-process
Python packages; the contract exists to keep the core shell and a lab apart.

## Ownership

Core owns the device, session store, WAL, uncertainty engine, plotting contracts and the
wizard state machine ([wizard framework](wizard.md)). A lab owns only its steps, its models, its analysis
and its exports.

## The `LabModule` protocol

- `id: LabId`, `title`, `models` (pydantic types the lab stores).
- `steps() -> list[StepSpec]`: frozen `StepSpec(id: StepId, title, phase: Phase,
  capture: CaptureKind, guidance: Callable[[RunState], str])`.
- `recompute(points) -> Result[AnalysisResult, ComputeError]`.
- `export_formats: tuple[ExportFormat, ...]`, each `(id, title, media_type, writer)` where the
  writer returns `Result[bytes, ComputeError]`.

`CaptureKind` is a `StrEnum`; core code dispatches with an exhaustive `match`
(see `needs_device`) so adding a kind is a type error until every site handles it.

## Registry

`LabRegistry.register(lab)` validates (non-empty id, at least one step, unique step ids,
unique export ids, unique lab id) and returns `Result[None, InputError]`.
`LabRegistry.from_plugins(plugin_registry)` builds a registry viewing the labs of every
enabled plugin; `add_plugins(plugin_registry)` adds them to an existing one and returns the
`InputError`s of labs that failed to register. A plugin that fails to load never reaches
the lab registry; it is a `failed` record in the `PluginRegistry`.
`discover()` is the deprecated path: it loads zero-arg factories from the legacy `sadi.labs`
entry-point group (logging a warning; use `sadi.plugins` instead) and returns the errors of
entries that failed; good entries still register. Built-in labs are registered by the app at
startup on the process-wide `REGISTRY`.

## Boundary enforcement

`test_labs_import_only_core_public_api` parses every file under `python/sadi/labs/<lab>/`
and fails on any `sadi.*` import other than public modules of `sadi.core`, `sadi.uncertainty`,
`sadi.logging_setup` or the lab's own package (no private `_modules`, no other lab).
Labs needing store event types (`EditV1`, `PointV1`, `PointWindow`) import them from
`sadi.core.events`, a public re-export, never from `sadi.store`.
Labs publishing exports (`write_export`, `render_csv`, `ExportResult`) use `sadi.core.export_api`,
a pure re-export of the store primitives, so atomic no-replace publish semantics are unchanged.

## Worked example: LCTT

The LCTT lab (`sadi/labs/lctt/`) is a built-in plugin (`sadi_plugin.toml`, id `lctt`) providing a `LabModule` whose steps are
calibration, elastic and plastic runs (`Phase`), whose `recompute` fits E from the captured
points, and whose exports are CSV and a report. Nothing in core names LCTT.

LCTT pieces so far: [settle detector](../lctt/settle.md), [creep fit](../lctt/creep.md), [calibration fit](../lctt/calibration.md), [slip detector](../lctt/slip.md).

