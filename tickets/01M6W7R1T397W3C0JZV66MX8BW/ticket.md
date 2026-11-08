+++
id = "01M6W7R1T397W3C0JZV66MX8BW"
title = "Name-collision check against typani exports (lint/grep gate)"
type = "chore"
category = "done"
outcome = "done"
priority = "medium"
points = 2
parent = "01M6W7R0EPXRHEMNEAB9QWVY57"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:35:14Z"
idempotency_key = "sadi-u6"
labels = ["ws:unc", "lint", "model:sonnet", "creates:tools/check_typani_collisions.py", "creates:python/tests/test_typani_collisions.py", "creates:docs/uncertainty/naming.md"]
scope = ["tools/check_typani_collisions.py", "python/tests/test_typani_collisions.py", "docs/uncertainty/naming.md", "docs/uncertainty/uncertain.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R155JD0XGVXHDSP19B1H"

[[acceptance]]
text = "Script introspects typani's current public exports and fails if any name is defined or re-exported in `sadi.uncertainty.__all__` (notably propagate, catching, Result, Ok, Err, unwrap, ErrorSet, UnwrapError), plus a grep for `import ... as propagate` style aliasing"
bound = true

[[acceptance]]
text = "Runs in pytest and is documented for the CI lint step (C1); also asserts `from typani import propagate` and `from sadi.uncertainty import uncertain` coexist"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
