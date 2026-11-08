+++
id = "01M6W7R3ZPY606D3MHG4QRM2GS"
title = "Binary WebSocket stream: trace frames, state and result push"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T05:39:49Z"
idempotency_key = "sadi-b5"
labels = ["ws:srv", "model:sonnet", "creates:python/sadi/server/ws.py", "creates:python/sadi/server/framing.py", "creates:python/tests/server/test_ws.py", "creates:docs/server/websocket.md"]
scope = ["python/sadi/server/ws.py", "python/sadi/server/framing.py", "python/tests/server/test_ws.py", "docs/server/websocket.md", "python/sadi/server/app.py", "docs/server/app.md", "docs/server/api.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R36G6BYYB4RBC60ZNFTD"

[[links]]
kind = "blocked-by"
target = "01M6W7R3XY1B0BF689RX3H80G2"

[[acceptance]]
text = "Binary frame spec (magic, type, seq, channel float32 min/max-decimated arrays, timestamp) documented byte-for-byte and mirrored by the TS decoder in F4; JSON side-channel for state/results/guidance"
bound = true

[[acceptance]]
text = "Back-pressure: slow clients drop display frames (never WAL data) with a counter; reconnect resumes from latest frame"
bound = true

[[acceptance]]
text = "Tested with 50 kS/s simulator at real time, frame rate and latency budget documented"
bound = true

[[acceptance]]
text = "Frame type reserved for the versioned results envelope defined by J4 (version, stale flag, progress)"
bound = true

[[acceptance]]
text = "Server tests cover codec round-trip, back-pressure counter, resume and 50 kS/s budget"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
