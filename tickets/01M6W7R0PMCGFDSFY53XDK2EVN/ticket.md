+++
id = "01M6W7R0PMCGFDSFY53XDK2EVN"
title = "Python scaffold: uv project, ruff, typani lint, pytest, core/ and labs/ layout"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 3
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:13:05Z"
idempotency_key = "sadi-p1"
labels = ["ws:py", "model:sonnet", "creates:python/pyproject.toml", "creates:python/sadi/__init__.py", "creates:python/sadi/core/__init__.py", "creates:python/sadi/labs/__init__.py", "creates:python/sadi/logging_setup.py", "creates:python/tests/conftest.py", "creates:docs/python-layout.md"]
scope = ["python/pyproject.toml", "python/sadi/__init__.py", "python/sadi/core/__init__.py", "python/sadi/labs/__init__.py", "python/sadi/logging_setup.py", "python/tests/conftest.py", "docs/python-layout.md", "python/tests/test_scaffold.py", "docs/index.md"]

[[acceptance]]
text = "uv-managed package `sadi` (python>=3.11) with deps fastapi, pydantic, typani, numpy, scipy, uvicorn; dev deps pytest, hypothesis, ruff, a type checker"
bound = true

[[acceptance]]
text = "Module logger helper per ~/.claude/refs/logging.md; layout: sadi/core (device, store, uncertainty, plotting contracts, wizard framework) and sadi/labs/<lab> (lab modules)"
bound = true

[[acceptance]]
text = "ruff, python -m typani.lint and pytest run clean on the empty skeleton; docs/python-layout.md states which ticket owns which package dir"
bound = true

[[acceptance]]
text = "pyproject also pins sympy, pint, hypothesis; package sadi/uncertainty is created by U1 (not P1)"
bound = true
+++

Serialisation point for pyproject.toml; later Python tickets must not edit it (widen lease if a dep is needed).

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
