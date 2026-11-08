+++
id = "01M6W7R3RXWS1WSH3TPXMK16Q2"
title = "Two-specimen workflow: long (elastic) and short (plastic) sample runs"
type = "task"
category = "in-progress"
priority = "high"
points = 5
parent = "01M6W7R06C7F7ZN0RC4CV3NWW5"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T05:17:48Z"
idempotency_key = "sadi-ts1"
labels = ["ws:py", "lctt", "oq:Q8", "model:sonnet", "creates:python/sadi/labs/lctt/lab.py", "creates:python/sadi/labs/lctt/specimens.py", "creates:python/tests/labs/lctt/test_lab.py", "creates:docs/lctt/lab-module.md"]
scope = ["python/sadi/labs/lctt/lab.py", "python/sadi/labs/lctt/specimens.py", "python/tests/labs/lctt/test_lab.py", "docs/lctt/lab-module.md", "python/sadi/labs/lctt/plugin.py", "python/tests/plugins/test_lctt_plugin.py", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R1G903HZ7V7JRCYC6ZT7"

[[links]]
kind = "blocked-by"
target = "01M6W7R335N9GPFD4DYXP2D6HY"

[[links]]
kind = "blocked-by"
target = "01M6W7R34VRSAYPG4SNQPQKQEK"

[[links]]
kind = "blocked-by"
target = "01M6W7R3J00J2HQ7XPW19WDD6Q"

[[acceptance]]
text = "Long sample (default L0 0.5 m, editable) supplies E; short sample (L0 0.08313 m) supplies plastic region/yield; results combine both with each sample's source stated"
bound = false

[[acceptance]]
text = "LCTT LabModule registered via PL1: steps Setup, Calibrate, Tare, Elastic, Plastic, Results, Export bound to phases (a) LVDT calibration, (b) elastic sample run, (c) plastic sample run (no Weights step: the weights/height inventory is a separate final-project plugin)"
bound = false

[[acceptance]]
text = "Calibration and experiment loads come from the core point inputs (heights, masses), so a plugin-supplied inventory with swapped weights needs no re-entry in the lab"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
