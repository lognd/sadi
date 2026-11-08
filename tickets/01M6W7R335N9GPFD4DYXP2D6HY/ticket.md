+++
id = "01M6W7R335N9GPFD4DYXP2D6HY"
title = "Wizard framework: step state machine, undo/redo command log, step rail data"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T03:12:33Z"
idempotency_key = "sadi-wiz1"
labels = ["ws:py", "model:sonnet", "creates:python/sadi/core/wizard.py", "creates:python/tests/core/test_wizard.py", "creates:docs/core/wizard.md"]
scope = ["python/sadi/core/wizard.py", "python/tests/core/test_wizard.py", "docs/core/wizard.md", "docs/core/lab-modules.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1G903HZ7V7JRCYC6ZT7"

[[links]]
kind = "blocked-by"
target = "01M6W7R2F3KJWQCWEKZK6BT3MG"

[[acceptance]]
text = "Wizard state derived from lab StepSpecs + session events: current step, completed steps, gated transitions (e.g. cannot Tare before Calibrate unless skipped explicitly), step rail projection for the UI"
bound = true

[[acceptance]]
text = "Undo/redo implemented as compensating WAL events (history never rewritten); tested for point capture, edit, window change"
bound = false

[[acceptance]]
text = "Every action returns typani Result with an error hint for the UI"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
