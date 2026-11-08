+++
id = "01M6WP9HGP60JCXMHC1E6E3EVV"
title = "packaging: declare sadi_py as an optional 'device' extra in python/pyproject.toml"
type = "task"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-08T04:22:31Z"
updated = "2026-11-08T04:23:11Z"
labels = ["creates:docs/packaging.md"]
scope = ["python/pyproject.toml", "docs/packaging.md", "docs/index.md", "python/tests/test_packaging_extras.py"]

[[acceptance]]
text = "pyproject declares the device optional-dependencies extra"
bound = true

[[acceptance]]
text = "docs/packaging.md explains maturin develop"
bound = true

[[acceptance]]
text = "a test asserts the extra exists"
bound = true
+++

sadi_py (maturin-built PyO3 extension in crates/sadi-py) is imported by doctor and the device path but is not declared anywhere in python/pyproject.toml. Add an optional-dependencies extra 'device' (and a uv source/path note) so a fresh checkout documents how to get it, without making the pure-Python install require a Rust toolchain. Document in docs. Acceptance: pyproject declares the extra; docs page explains maturin develop; a test asserts the extra exists.
