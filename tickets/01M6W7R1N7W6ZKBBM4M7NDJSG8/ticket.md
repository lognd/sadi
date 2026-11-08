+++
id = "01M6W7R1N7W6ZKBBM4M7NDJSG8"
title = "Creep fit: strain vs log-time per hold"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:51:59Z"
idempotency_key = "sadi-cr1"
labels = ["ws:py", "lctt", "oq:Q9", "model:sonnet", "creates:python/sadi/labs/lctt/creep.py", "creates:python/tests/labs/lctt/test_creep.py", "creates:docs/lctt/creep.md"]
scope = ["python/sadi/labs/lctt/creep.py", "python/tests/labs/lctt/test_creep.py", "docs/lctt/creep.md", "docs/core/lab-modules.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0XB2WMP03ZGW8XCPH41"

[[links]]
kind = "blocked-by"
target = "01M6W7R13KW0FFYHZJ7FY28A3R"

[[links]]
kind = "blocked-by"
target = "01M6W7R155JD0XGVXHDSP19B1H"

[[acceptance]]
text = "Per-hold fit strain = a + b*ln(t - t_load) with standard errors, r^2, extrapolated strain at a reference time, with uncertainty; handles short holds with a typed error"
bound = true

[[acceptance]]
text = "Recovers injected creep slope from simulator creeping scenario within tolerance"
bound = true

[[acceptance]]
text = "Feeds the creep strain-vs-log-time plot and the settle/forced-early decision rationale"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
