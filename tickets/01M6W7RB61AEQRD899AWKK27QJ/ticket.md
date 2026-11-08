+++
id = "01M6W7RB61AEQRD899AWKK27QJ"
title = "Backend e2e suite: simulator fault injection (noise, drift, creep, slip, dropped bytes, saturation)"
type = "task"
category = "in-progress"
priority = "high"
points = 8
parent = "01M6W7R0D1R7J4VQJVKGX8YEZ9"
reporter = "lognd"
created = "2026-11-08T00:08:28Z"
updated = "2026-11-08T06:23:19Z"
idempotency_key = "sadi-t1"
labels = ["ws:qa", "fault-injection", "model:sonnet", "creates:python/tests/e2e/**", "creates:docs/testing.md"]
scope = ["python/tests/e2e/**", "docs/testing.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0YWS8EXHXFBNZCE4AHC"

[[links]]
kind = "blocked-by"
target = "01M6W7R257EXZX1RD7VT3M5GJG"

[[links]]
kind = "blocked-by"
target = "01M6W7R2M88JFNKRESHJBD8YVD"

[[links]]
kind = "blocked-by"
target = "01M6W7R2ZMZSCRWKCRFHAH4MTB"

[[links]]
kind = "blocked-by"
target = "01M6W7R3N96SVM2D2GQQTA833F"

[[links]]
kind = "blocked-by"
target = "01M6W7R3RXWS1WSH3TPXMK16Q2"

[[links]]
kind = "blocked-by"
target = "01M6W7R3ZPY606D3MHG4QRM2GS"

[[links]]
kind = "blocked-by"
target = "01M6W7RAY4KTF866Q0Y7B4SZGG"

[[acceptance]]
text = "Parametrised full-run scenarios through API: each FaultPlan (noise, drift, creep, slip steps, dropped bytes, saturation, combined) asserts settle behaviour, slip flagged, saturation warning, byte resync with counted gaps, results within tolerance of ground truth, raw preserved in WAL"
bound = false

[[acceptance]]
text = "A kill-during-run scenario recovers the session and continues with a new version"
bound = false

[[acceptance]]
text = "docs/testing.md documents the scenario matrix and how to add one"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
