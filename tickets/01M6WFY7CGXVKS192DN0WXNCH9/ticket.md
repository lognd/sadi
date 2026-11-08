+++
id = "01M6WFY7CGXVKS192DN0WXNCH9"
title = "Plugin system: first-class plugins; lctt and the final project become plugins"
type = "epic"
category = "todo"
priority = "high"
reporter = "lognd"
created = "2026-11-08T02:31:29Z"
updated = "2026-11-08T02:31:29Z"
labels = ["plugins"]

[[acceptance]]
text = "All child tickets done"
bound = false

[[acceptance]]
text = "Core test suite passes with private/ absent"
bound = false

[[acceptance]]
text = "lctt loads via the same path as third-party plugins"
bound = false
+++

Design: docs/plugins.md. Goal: a plugin = Python package + manifest (id, version, api_version range, contributions, requires). Contributes labs now; exports, jobs, frontend panels later. Sources: (1) built-in first-party (lctt, no special casing), (2) sadi.plugins entry points, (3) gitignored local dirs (plugins/, private/*/plugin) via SADI_PLUGIN_PATH or settings. Failures are Result/ErrorSet, a broken plugin never takes down core or touches session data (plugins get only core public API, never WAL/store). State visible in doctor (step-by-step fixes), CLI (sadi plugins list/info/enable/disable) and server list endpoint. Sessions record plugin id+version. private/final-project must never be tracked or imported from tracked code; public repo works without it.
