# Packaging and the device extra

Status: current

The `sadi` Python package is pure Python and installs without a Rust
toolchain. The device path (and `sadi-doctor`) additionally imports
`sadi_py`, a PyO3 extension built by maturin from `crates/sadi-py`.

## The `device` extra

`python/pyproject.toml` declares an optional-dependencies extra named
`device`:

```
pip install "sadi[device]"
```

The extra is intentionally empty: `sadi_py` is not published to PyPI, so it
cannot be named as a dependency without forcing a Rust build. The extra is
the documented marker for "this install is meant to drive hardware"; the
extension itself is built locally as below.

## Building sadi_py

From a fresh checkout, with a Rust toolchain and maturin available:

```
cd crates/sadi-py
maturin develop
```

`maturin develop` builds the extension and installs it into the active
virtual environment (for example the one created by `uv sync` in `python/`).
Without it, the pure-Python parts of SADI still work; device features and the
related doctor checks report the extension as missing.
