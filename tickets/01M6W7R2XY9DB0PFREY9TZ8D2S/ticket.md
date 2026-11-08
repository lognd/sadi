+++
id = "01M6W7R2XY9DB0PFREY9TZ8D2S"
title = "LCTT tare and strain/stress/load with RSS uncertainty"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T03:10:44Z"
idempotency_key = "sadi-a2"
labels = ["ws:py", "lctt", "oq:Q5", "oq:Q10", "oq:Q8", "model:sonnet", "creates:python/sadi/labs/lctt/loading.py", "creates:python/tests/labs/lctt/test_loading.py", "creates:docs/lctt/loading.md"]
scope = ["python/sadi/labs/lctt/loading.py", "python/tests/labs/lctt/test_loading.py", "docs/lctt/loading.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1RD3P97HFFDZ2NVD83Y"

[[links]]
kind = "blocked-by"
target = "01M6W7R26WGJ0TZ4GS8N0YH4FG"

[[links]]
kind = "blocked-by"
target = "01M6W7R28HX7237GMXSNQKWT3Y"

[[acceptance]]
text = "Tare pooling (voltage + uncertainty), load = sum of inventory masses * g (+ hanger) with U, area from diameter with U, stress, strain = slope*dV/L0 with U, all through U1"
bound = true

[[acceptance]]
text = "Options with documented defaults: U_V = 2 s of block (Q5; alt 2 s/sqrt(N)), LVDT sign handling warn-or-flip (Q10 default warn plus one-click flip), L0 default per specimen (Q8: short 0.08313 m, long 0.5 m, always editable)"
bound = false

[[acceptance]]
text = "Validated against docs oracle expected_values.py for the local short-run file within 1e-9 relative (excluding documented-bug columns)"
bound = false

[[acceptance]]
text = "Load, stress, strain are written once as plain @uncertain functions; .latex of each is available to the results panel and report"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
