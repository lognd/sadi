+++
id = "01M6W7R3XY1B0BF689RX3H80G2"
title = "FastAPI app: REST endpoints (sessions, inventory, points, results, export)"
type = "task"
category = "in-progress"
priority = "high"
points = 8
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T00:08:20Z"
updated = "2026-11-08T05:32:56Z"
idempotency_key = "sadi-b4"
labels = ["ws:srv", "model:sonnet", "creates:python/sadi/server/app.py", "creates:python/sadi/server/routes/**", "creates:python/sadi/server/schemas.py", "creates:python/tests/server/test_routes.py", "creates:docs/server/api.md"]
scope = ["python/sadi/server/app.py", "python/sadi/server/routes/**", "python/sadi/server/schemas.py", "python/tests/server/test_routes.py", "docs/server/api.md", "python/sadi/store/session.py", "python/sadi/server/service.py", "python/tests/server/test_routes_problem.py", "python/tests/store/test_session_held_root.py", "docs/server/app.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R13KW0FFYHZJ7FY28A3R"

[[links]]
kind = "blocked-by"
target = "01M6W7R1G903HZ7V7JRCYC6ZT7"

[[links]]
kind = "blocked-by"
target = "01M6W7R26WGJ0TZ4GS8N0YH4FG"

[[links]]
kind = "blocked-by"
target = "01M6W7R335N9GPFD4DYXP2D6HY"

[[links]]
kind = "blocked-by"
target = "01M6W7R36G6BYYB4RBC60ZNFTD"

[[links]]
kind = "blocked-by"
target = "01M6W7R3J00J2HQ7XPW19WDD6Q"

[[links]]
kind = "blocked-by"
target = "01M6W7R3W8RJPVS0VVDG2YNMJB"

[[acceptance]]
text = "Session create/open/resume, wizard state and transitions, capture/undo/redo/edit point and history endpoints, writes via the WAL"
bound = true

[[acceptance]]
text = "Handlers map typani errors to problem+json with a what-to-do hint; no business logic in handlers"
bound = false

[[acceptance]]
text = "Tested with httpx (TestClient) against the real WAL and the lctt lab"
bound = false
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
