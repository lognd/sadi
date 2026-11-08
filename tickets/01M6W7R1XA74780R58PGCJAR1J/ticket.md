+++
id = "01M6W7R1XA74780R58PGCJAR1J"
title = "store/session: versioned O_EXCL session dirs, manifest, lock, resume"
type = "task"
category = "done"
outcome = "done"
priority = "critical"
points = 5
parent = "01M6W7R04QJTECCTSV9EY2JADK"
reporter = "lognd"
created = "2026-11-08T00:08:18Z"
updated = "2026-11-08T00:49:46Z"
idempotency_key = "sadi-ds4"
labels = ["ws:store", "model:sonnet", "creates:python/sadi/store/session.py", "creates:python/sadi/store/manifest.py", "creates:python/tests/store/test_session.py", "creates:docs/store/session.md"]
scope = ["python/sadi/store/session.py", "python/sadi/store/manifest.py", "python/tests/store/test_session.py", "docs/store/session.md", "docs/index.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R0T0AC47BJGF2CKTER59"

[[links]]
kind = "blocked-by"
target = "01M6W7R1883HHXY4XYEJA5DMTN"

[[acceptance]]
text = "create_session never reuses or overwrites a directory (O_EXCL; collision gets next version); resume creates a new version with parent link"
bound = true

[[acceptance]]
text = "Manifest (pydantic) written via atomic replace; single-writer lock file with stale-lock handling per OS"
bound = true

[[acceptance]]
text = "Opening a session read-only for review never mutates it; tests prove existing sessions are byte-identical after open/close"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
