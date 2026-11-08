+++
id = "01M6W7R1KH0MVS56MX07Q9BX19"
title = "Settle detector: rolling LVDT drift slope, threshold and minimum dwell"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:30:06Z"
idempotency_key = "sadi-s1"
labels = ["ws:py", "lctt", "oq:Q9", "model:sonnet", "creates:python/sadi/labs/lctt/settle.py", "creates:python/tests/labs/lctt/test_settle.py", "creates:docs/lctt/settle.md"]
scope = ["python/sadi/labs/lctt/settle.py", "python/tests/labs/lctt/test_settle.py", "docs/lctt/settle.md", "python/sadi/labs/lctt/__init__.py", "docs/core/lab-modules.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0XB2WMP03ZGW8XCPH41"

[[links]]
kind = "blocked-by"
target = "01M6W7R13KW0FFYHZJ7FY28A3R"

[[acceptance]]
text = "Pure detector over a time/LVDT window: trailing least-squares slope with standard error vs configurable threshold and minimum dwell; typed Result; slope as Measured; unit-tested for settle, drift, noise, short input and dwell boundary"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
