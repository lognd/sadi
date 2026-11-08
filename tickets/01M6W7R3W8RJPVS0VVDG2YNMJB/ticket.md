+++
id = "01M6W7R3W8RJPVS0VVDG2YNMJB"
title = "Guided run engine: phase-wise next-step guidance and confidence status"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R081S67XNGBH79ACCBZZ"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T05:21:34Z"
idempotency_key = "sadi-ph1"
labels = ["ws:plan", "lctt", "model:sonnet", "creates:python/sadi/labs/lctt/guidance.py", "creates:python/tests/labs/lctt/test_guidance.py", "creates:docs/lctt/guidance.md"]
scope = ["python/sadi/labs/lctt/guidance.py", "python/tests/labs/lctt/test_guidance.py", "docs/lctt/guidance.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R39TND6SN4ENN93ZD322"

[[links]]
kind = "blocked-by"
target = "01M6W7R3J00J2HQ7XPW19WDD6Q"

[[links]]
kind = "blocked-by"
target = "01M6W7R3RXWS1WSH3TPXMK16Q2"

[[acceptance]]
text = "For each phase (calibrate, elastic, plastic) returns next action text ('Use weights 3, 5, 6'; 'Wait: creeping'; 'Press Space to accept'), expected value, running confidence indicator (current half-width vs user target), and stop-early recommendation"
bound = true

[[acceptance]]
text = "Phase transition proposed (never forced) when confidence is enough; user can ignore and continue"
bound = true

[[acceptance]]
text = "Simulator end-to-end: a full three-phase run completes in a bounded number of points (documented), guidance never suggests unsafe/out-of-range load"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
