# Python layout

Status: current

The Python package `sadi` lives in `python/` and is managed by uv
(`python/pyproject.toml`, owned by P1 ~XDK2EVN; later Python tickets must not
edit it, they widen their lease if a dependency is needed).

Tooling is the Astral stack only: uv (envs, `dev` dependency group, lockfile
`python/uv.lock`), ruff (lint and format) and ty (types; configured under
`[tool.ty]`, all rules errors). Run from `python/`:

```
uv sync
uv run ruff check
uv run ruff format --check
uv run ty check
uv run pytest
uv run python -m typani.lint sadi
```

The venv lives in `python/.venv` (gitignored).

## Logging

Use `from sadi.logging_setup import get_logger; _log = get_logger(__name__)`.
Never `print`. The module is named `logging_setup` so it cannot shadow stdlib `logging`.
Handlers resolve `sys.stdout` (DEBUG/INFO) and `sys.stderr` (WARNING+) at emit time, so stream
redirection and pytest capture work regardless of when `get_logger` was first called.

## Naming rule

typani exports `propagate`, `catching`, `Result`, `Ok`, `Err`, `unwrap`; no sadi
module or public API may define those names.

## Package ownership

| Path | Owner ticket |
|---|---|
| `python/pyproject.toml`, `sadi/__init__.py`, `sadi/logging_setup.py`, `tests/conftest.py` | P1 ~XDK2EVN |
| `sadi/core/` models and error taxonomy | P2 ~FY28A3R |
| `sadi/core/` device wrapper | B2 ~GX511CP |
| `sadi/store/` (durable, wal, session, events, snapshot, exports) | DS2-DS7 |
| `sadi/core/` wizard framework | WIZ1 ~XP2D6HY |
| `sadi/core/` LabModule contract | PL1 ~CYC6ZT7 |
| `sadi/uncertainty/` | U1 ~SP19B1H (created by U1, not P1) |
| `sadi/labs/lctt/` | A1-A4, TS1 and related |
| `sadi/labs/__init__.py`, `sadi/core/__init__.py` | P1 (empty skeleton) |
