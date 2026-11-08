+++
id = "01M6W7R0EPXRHEMNEAB9QWVY57"
title = "Uncertainty engine: sadi.uncertainty (Measured, @uncertain)"
type = "epic"
category = "todo"
priority = "high"
parent = "01M6W78507Q819RQ7VXNFZEVFY"
reporter = "lognd"
created = "2026-11-08T00:08:17Z"
updated = "2026-11-08T00:08:17Z"
idempotency_key = "sadi-e_unc"
labels = ["ws:unc"]
+++

Workstream: first-class uncertainty handling so the lab author never thinks about it. Pure Python, pydantic, typani Results. Package `sadi.uncertainty`; decorator `@uncertain` (NOT `propagate`: that name belongs to typani).

Suggested model: n/a.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001).
