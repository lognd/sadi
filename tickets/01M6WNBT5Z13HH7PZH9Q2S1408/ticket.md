+++
id = "01M6WNBT5Z13HH7PZH9Q2S1408"
title = "sadi-py: reconcile sim stubs (__init__.pyi class sim vs sim.pyi), expose SessionConfig on sim.open, add crates/sadi-py/tests to pytest testpaths"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T04:06:17Z"
updated = "2026-11-08T04:10:46Z"
labels = ["rust"]
scope = ["crates/sadi-py/**", "docs/device/python-binding.md", "creates:changelog.d/**"]

[[acceptance]]
text = "sim.open accepts a SessionConfig and stubs agree"
bound = true

[[acceptance]]
text = "sim.rs Rust unit tests and crates/sadi-py/tests run in the suites"
bound = true
+++

From ~JBD8YVD. Also run the Rust unit tests for sim.rs via goway (only compiled/clippy-checked locally).
