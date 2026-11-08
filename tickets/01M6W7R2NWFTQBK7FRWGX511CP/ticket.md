+++
id = "01M6W7R2NWFTQBK7FRWGX511CP"
title = "Device service: sadi_py wrapper returning typani Results, reconnect, sim/real select"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 5
parent = "01M6W7R09P668G2VDDAWEDCSRM"
reporter = "lognd"
created = "2026-11-08T00:08:19Z"
updated = "2026-11-08T02:15:11Z"
idempotency_key = "sadi-b2"
labels = ["ws:srv", "model:sonnet", "creates:python/sadi/core/device.py", "creates:python/tests/core/test_device.py", "creates:docs/core/device.md", "creates:python/sadi/core/phases.py", "creates:python/tests/core/test_phases.py"]
scope = ["python/sadi/core/device.py", "python/tests/core/test_device.py", "docs/core/device.md", "python/sadi/core/phases.py", "python/tests/core/test_phases.py", "docs/index.md", "docs/README.md"]

[[links]]
kind = "blocked-by"
target = "01M6W7R13KW0FFYHZJ7FY28A3R"

[[links]]
kind = "blocked-by"
target = "01M6W7R226VMAMHYPDBQTAS277"

[[acceptance]]
text = "DeviceService opens simulator or serial port (auto-detect FTDI), start/stop streaming, converts sadi_py exceptions to typani Results with 'what to do' hints, reconnect/backoff, status (connected|simulated|error)"
bound = true

[[acceptance]]
text = "Reader runs in a dedicated thread/task; no data loss under slow consumers (bounded queue with loud overflow error, never silent drop)"
bound = true

[[acceptance]]
text = "Typed Python wrapper over the sadi-py Session: one class per session phase (Disconnected, Connected, Streaming, Stopped), each transition consumes the previous object so misuse fails type-check and at runtime; phase classes documented in docs/core/device.md"
bound = true
+++

Suggested model: Sonnet.
Standards: ASCII only, no emojis; module logger (never print) logging every state change, boundary, branch and error path; one-line WHY/WHAT docstring on every public symbol; update the ticket's docs file in the same change; tests in the same change; stay inside scope (frob lease widen on SCOPE001). Python: typani Result[T, E] for every fallible operation (exceptions only for programmer bugs), pydantic models, run python -m typani.lint on new code.
