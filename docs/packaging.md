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

From a fresh checkout, with a Rust toolchain and uv available (maturin is not
in the `python/` environment, so it runs through `uvx`; `VIRTUAL_ENV` points
it at `python/.venv`, created by `uv sync` in `python/`):

```
cd crates/sadi-py
VIRTUAL_ENV=../../python/.venv uvx maturin develop --release --uv
```

On Windows PowerShell: `$env:VIRTUAL_ENV = '..\..\python\.venv'; uvx maturin develop --release --uv`.

`maturin develop` builds the extension and installs it into the active
virtual environment (for example the one created by `uv sync` in `python/`).
Without it, the pure-Python parts of SADI still work; device features and the
related doctor checks report the extension as missing.

## Bundling the web UI

Windows and macOS are UNVERIFIED. The build script uses only pathlib and
subprocess, but it has been exercised on Linux alone.

One command, from a clean checkout (needs Node.js with npm on PATH):

```
cd python && uv run python ../packaging/build_ui.py
```

It runs `npm ci` and `npm run build` (tsc + vite build) in `web/`, then
replaces the contents of `python/sadi/_ui/` with `web/dist`. Pass
`--no-install` to skip `npm ci`. The copied files are gitignored; only
`python/sadi/_ui/.gitkeep` is tracked. `python/pyproject.toml` lists
`sadi/_ui/**` as hatch wheel `artifacts`, so a wheel built after the UI
step contains the UI; the `sadi` console script (`sadi.launcher:main`) is
declared in `[project.scripts]`.

At runtime the launcher picks the UI directory in this order: `--web-dist`
if given, then the packaged `sadi/_ui` (when it holds `index.html`), then
`web/dist` relative to the working directory.

Not yet verified: that a built wheel actually contains the UI (needs a wheel
build, deferred to the release-workflow ticket) and any run on Windows or
macOS.

Release builds and the manual publish gate are described in [Release procedure](release.md).
