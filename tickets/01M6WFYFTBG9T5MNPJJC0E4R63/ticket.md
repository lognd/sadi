+++
id = "01M6WFYFTBG9T5MNPJJC0E4R63"
title = "Plugin manifest model and api_version compatibility"
type = "task"
category = "in-progress"
priority = "high"
points = 3
parent = "01M6WFY7CGXVKS192DN0WXNCH9"
reporter = "lognd"
created = "2026-11-08T02:31:38Z"
updated = "2026-11-08T02:46:12Z"
labels = ["plugins", "creates:python/sadi/plugins/__init__.py", "creates:python/sadi/plugins/manifest.py", "creates:python/sadi/plugins/errors.py", "creates:python/tests/plugins/test_manifest.py"]
scope = ["python/sadi/plugins/__init__.py", "python/sadi/plugins/manifest.py", "python/sadi/plugins/errors.py", "python/tests/plugins/test_manifest.py", "python/pyproject.toml", "python/uv.lock"]

[[acceptance]]
text = "Valid manifest round-trips toml -> model"
bound = true

[[acceptance]]
text = "Malformed/missing fields yield Err(PluginManifestError), never raise"
bound = true

[[acceptance]]
text = "Incompatible api_version yields Err(PluginApiVersionError) naming both versions"
bound = true

[[acceptance]]
text = "python -m typani.lint clean; frob check --ticket passes"
bound = true
+++

Create package sadi.plugins. PluginManifest (pydantic, frozen): id (slug), version (PEP 440), api_version (specifier range), contributions (labs: list of entrypoint refs now; exports/jobs/panels reserved, default empty), requires (list of plugin id + range). PLUGIN_API_VERSION constant. check_api_compat(manifest) -> Result[None, PluginApiVersionError]. load_manifest_toml(path) -> Result[PluginManifest, PluginManifestError]. Typed error classes in errors.py. Module logger, docstrings, no exceptions for expected failures. See docs/plugins.md.
