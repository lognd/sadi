# sadi-py

PyO3/maturin bindings over sadi-proto. See `docs/device/python-binding.md`.

    uv venv && uv pip install numpy pytest
    uvx maturin develop --release --uv && pytest

To install into `python/.venv` instead, prefix with
`VIRTUAL_ENV=../../python/.venv` (PowerShell: `$env:VIRTUAL_ENV = '..\..\python\.venv';`).
