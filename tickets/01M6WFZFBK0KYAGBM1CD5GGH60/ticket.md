+++
id = "01M6WFZFBK0KYAGBM1CD5GGH60"
title = "Session provenance: record plugin id+version per run, warn on reopen"
type = "task"
category = "in-progress"
priority = "high"
points = 3
parent = "01M6WFY7CGXVKS192DN0WXNCH9"
reporter = "lognd"
created = "2026-11-08T02:32:10Z"
updated = "2026-11-08T02:53:19Z"
labels = ["plugins", "creates:python/tests/store/test_session_plugin_provenance.py"]
scope = ["python/sadi/store/manifest.py", "python/sadi/store/session.py", "python/tests/store/test_session_plugin_provenance.py"]

[[links]]
kind = "blocked-by"
target = "01M6WFYN8C6YH5D79CPEKSP69P"

[[acceptance]]
text = "New session manifest contains plugin id+version"
bound = true

[[acceptance]]
text = "Old manifest without the field still reopens"
bound = true

[[acceptance]]
text = "Reopen with plugin absent opens successfully with a warning naming the plugin"
bound = false

[[acceptance]]
text = "Existing store tests pass"
bound = false
+++

Add optional plugins: list[SessionPluginRef(id, version)] to the session manifest (schema version bump or backward-compatible optional field; old sessions without it must still open). Core records provenance via an API argument, plugin code never touches the manifest. On reopen/recovery compare to PluginRegistry and return a warning list (missing plugin, version differs) as part of a Result, never a hard failure: data stays readable without the plugin. Data-safety: do not alter WAL record format.
