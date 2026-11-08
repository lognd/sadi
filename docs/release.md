# Release procedure

Status: current

Releases are built by `.github/workflows/wheels.yml`. The workflow builds
artifacts only; it never publishes to PyPI. Publishing is a manual gate.

## Status

UNVERIFIED: the workflow has not been run. It was written and its YAML and
structure checked locally (`python/tests/packaging/test_wheels_workflow.py`),
but no GitHub runner has executed it. Windows and macOS in particular are
UNVERIFIED, for the web UI build, the maturin wheels and the smoke test.
Expect to fix the first run.

## What the workflow does

Triggers: a pushed tag matching `v*`, or `workflow_dispatch` from the Actions
tab.

1. `sadi-wheel` (Linux): `python packaging/build_ui.py` builds the web UI into
   `python/sadi/_ui`, then `python -m build --wheel python` produces the
   pure-Python `sadi` wheel. A check fails the job if the wheel lacks
   `sadi/_ui/index.html`.
2. `sadi-py-wheels`: `PyO3/maturin-action` builds `crates/sadi-py` for Linux
   x86_64 (manylinux), Windows x64, macOS x86_64 and macOS arm64.
3. `smoke` on Linux, Windows and macOS: creates a clean venv, installs the
   `sadi` and `sadi-py` wheels from the downloaded artifacts, then runs
   `sadi --version` and `sadi --sim --no-browser --selftest`. Both must exit 0.

Wheels are uploaded as workflow artifacts (`wheel-*`).

## Procedure

1. Update versions in `python/pyproject.toml` and `crates/sadi-py`
   (`pyproject.toml` and `Cargo.toml`), and merge to main with CI green.
2. Tag `vX.Y.Z` and push the tag, or run the workflow by hand.
3. Wait for all jobs, including all three smoke jobs, to pass.
4. Download the `wheel-*` artifacts and inspect them.
5. Publish manually, for example `twine upload` of the reviewed wheels. This
   step is deliberately not automated.

See also [Packaging and the device extra](packaging.md).
