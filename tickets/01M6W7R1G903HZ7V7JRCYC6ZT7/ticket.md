+++
id = "01M6W7R1G903HZ7V7JRCYC6ZT7"
title = "Lab-module boundary: core shell vs lab plugin contract (LabModule protocol)"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:27:34Z"
idempotency_key = "sadi-pl1"
labels = ["ws:py", "architecture", "model:sonnet", "creates:python/sadi/core/lab.py", "creates:python/sadi/core/registry.py", "creates:python/tests/core/test_lab_registry.py", "creates:docs/core/lab-modules.md"]
scope = ["python/sadi/core/lab.py", "python/sadi/core/registry.py", "python/tests/core/test_lab_registry.py", "docs/core/lab-modules.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R13KW0FFYHZJ7FY28A3R"

[[acceptance]]
text = "LabModule protocol: id, title, steps() -> list[StepSpec] (id, title, phase, capture kind, guidance hook), models (pydantic types), analysis hooks (recompute(points, inventory) -> Result), export formats (id, writer); discovered via entry points `sadi.labs` and a built-in registry"
bound = true

[[acceptance]]
text = "Core owns device, session store, WAL, uncertainty engine, plotting contracts and wizard state machine; a lab module may only depend on core public API (import-linter or arch test enforces this)"
bound = true

[[acceptance]]
text = "Documented with the LCTT lab as the worked example; explicitly NOT a general plugin system (no sandboxing, no hot reload)"
bound = true
+++

Keep the boundary clean, do not over-engineer. Other labs are future work.

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
