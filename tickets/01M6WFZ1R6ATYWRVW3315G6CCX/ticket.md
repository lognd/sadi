+++
id = "01M6WFZ1R6ATYWRVW3315G6CCX"
title = "Local-dir plugin source (plugins/, private/*/plugin) with settings and gitignore"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
parent = "01M6WFY7CGXVKS192DN0WXNCH9"
reporter = "lognd"
created = "2026-11-08T02:31:56Z"
updated = "2026-11-08T02:52:13Z"
labels = ["plugins", "creates:python/sadi/plugins/local.py", "creates:python/sadi/plugins/settings.py", "creates:python/tests/plugins/test_local_source.py"]
scope = [".gitignore", "python/sadi/plugins/local.py", "python/sadi/plugins/settings.py", "python/tests/plugins/test_local_source.py"]

[[links]]
kind = "blocked-by"
target = "01M6WFYN8C6YH5D79CPEKSP69P"

[[acceptance]]
text = "Plugin in a tmp dir loads with no pip install"
bound = true

[[acceptance]]
text = "Absent default dirs yield Ok with zero plugins"
bound = false

[[acceptance]]
text = "Broken plugin dir yields a failed record, others still load"
bound = false

[[acceptance]]
text = "git check-ignore plugins/x passes"
bound = false
+++

LocalDirSource loads plugins by path without install: scans SADI_PLUGIN_PATH (os.pathsep list) or settings plugin_paths; defaults plugins/ and private/*/plugin relative to repo root when present. Each plugin dir needs sadi_plugin.toml; importlib spec_from_file_location under a namespaced module name (sadi_local_plugins.<id>) so it never shadows core. Missing dirs are not errors; unreadable/invalid ones yield per-plugin PluginSourceError records. Add plugins/ to .gitignore (private/ already ignored). PluginSettings pydantic model (plugin_paths, config dir for enable/disable state).
