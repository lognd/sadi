+++
id = "01M6WFYN8C6YH5D79CPEKSP69P"
title = "Plugin loader and PluginRegistry generalizing LabRegistry"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6WFY7CGXVKS192DN0WXNCH9"
reporter = "lognd"
created = "2026-11-08T02:31:43Z"
updated = "2026-11-08T02:49:55Z"
labels = ["plugins", "creates:python/sadi/plugins/registry.py", "creates:python/sadi/plugins/sources.py", "creates:python/tests/plugins/test_registry.py"]
scope = ["python/sadi/core/registry.py", "python/sadi/core/lab.py", "python/tests/core/test_lab_registry.py", "python/sadi/plugins/registry.py", "python/sadi/plugins/sources.py", "python/tests/plugins/test_registry.py", "python/sadi/plugins/__init__.py", "python/sadi/plugins/errors.py"]

[[links]]
kind = "blocked-by"
target = "01M6WFYFTBG9T5MNPJJC0E4R63"

[[acceptance]]
text = "Existing test_lab_registry.py passes unchanged"
bound = true

[[acceptance]]
text = "A plugin raising at import yields a failed record; other plugins and core still load"
bound = true

[[acceptance]]
text = "Duplicate id and unmet requires produce distinct typed errors"
bound = true

[[acceptance]]
text = "Disabled plugins are recorded but not imported"
bound = true
+++

PluginSource protocol (discover() -> Result[list[PluginCandidate], ErrorSet]); BuiltinSource (explicit first-party list) and EntryPointSource (group sadi.plugins). PluginRegistry.discover(sources, disabled) builds a PluginRecord per plugin (state enabled/disabled/failed/incompatible, errors); import+register guarded so any exception becomes PluginImportError on that record only; duplicate ids and unmet requires reported per record; deterministic order. LabRegistry keeps its public API (validate_lab, discover, REGISTRY) as a view over PluginRegistry; legacy sadi.labs entry-point group still read with a deprecation log. Update lab.py docstring (remove 'NOT a general plugin system'). Plugins get only core public API; registry never hands them store/WAL handles.
