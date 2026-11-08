+++
id = "01M6WN9FATNMDVP10GGDEC40NP"
title = "sadi-py: expose __version__, PROTOCOL_VERSION, serial_features() and selftest() for doctor EXT-020/040/050"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T04:05:00Z"
updated = "2026-11-08T04:06:57Z"
labels = ["rust"]
scope = ["creates:crates/sadi-py/src/meta.rs", "crates/sadi-py/src/lib.rs", "crates/sadi-py/src/errors.rs", "crates/sadi-py/Cargo.toml", "crates/sadi-py/python/sadi_py/__init__.py", "crates/sadi-py/python/sadi_py/__init__.pyi", "docs/device/python-binding.md", "creates:crates/sadi-py/python/sadi_py/tests/test_meta.py"]
+++

From ~A2YBMPV: doctor reads these via getattr and skips when missing, so EXT-020/040/050 are unverified. Add them to the sadi-py bindings (safe Rust, build via goway).
