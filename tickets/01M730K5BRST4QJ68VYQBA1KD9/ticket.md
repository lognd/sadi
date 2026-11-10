+++
id = "01M730K5BRST4QJ68VYQBA1KD9"
title = "Ship an example lab plugin (tracked, loadable via SADI_PLUGIN_PATH) as a worked demo"
type = "story"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-10T15:17:59Z"
updated = "2026-11-10T15:19:56Z"
labels = ["creates:python/tests/plugins/test_example_plugin.py", "creates:examples/**"]
scope = ["examples/**", "python/tests/plugins/test_example_plugin.py", "docs/plugins.md"]

[[acceptance]]
text = "examples/plugins/example-lab/ has sadi_plugin.toml and a package contributing one small lab using only the public core API"
bound = true

[[acceptance]]
text = "A test loads it via LocalDirSource/SADI_PLUGIN_PATH and asserts it is discovered, enabled and its lab steps run"
bound = false

[[acceptance]]
text = "docs/plugins.md section 11 points to the example; sadi plugins list shows it when SADI_PLUGIN_PATH is set"
bound = false
+++

User asked to ship a lab as a plugin just as an example. plugins/ is gitignored, so the example lives under examples/plugins/. Based on the README make-a-plugin walkthrough; must not import private/ or labview/.
