+++
id = "01M6W7R257EXZX1RD7VT3M5GJG"
title = "Slip detector: sudden strain steps without load change"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T01:20:29Z"
idempotency_key = "sadi-cr2"
labels = ["ws:py", "lctt", "fault-injection", "model:sonnet", "creates:python/sadi/labs/lctt/slip.py", "creates:python/tests/labs/lctt/test_slip.py", "creates:python/tests/fixtures/short_slip/**", "creates:docs/lctt/slip.md"]
scope = ["python/sadi/labs/lctt/slip.py", "python/tests/labs/lctt/test_slip.py", "python/tests/fixtures/short_slip/**", "docs/lctt/slip.md", "docs/core/lab-modules.md", "docs/README.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0XB2WMP03ZGW8XCPH41"

[[links]]
kind = "blocked-by"
target = "01M6W7R1N7W6ZKBBM4M7NDJSG8"

[[acceptance]]
text = "Classifies a strain change at constant load as creep (smooth, log-time decaying) vs slip (step-like, exceeds k*noise, not fitted by log-time); outputs events with time, size, confidence"
bound = true

[[acceptance]]
text = "Detects 100% of injected slip steps above size threshold with false-positive rate below a documented bound on simulator noise scenarios"
bound = true

[[acceptance]]
text = "the local short-run file used ONLY as a slip-contaminated test case (fixture; expected flagged rows documented), not as calibration for physics"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
