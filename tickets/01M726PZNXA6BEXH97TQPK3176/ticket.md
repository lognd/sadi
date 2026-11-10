+++
id = "01M726PZNXA6BEXH97TQPK3176"
title = "H3: stress-strain refit must use the open session, not newest dir"
type = "bug"
category = "in-progress"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T07:45:41Z"
updated = "2026-11-10T07:50:23Z"
labels = ["creates:python/tests/server/test_curve_source_open_session.py"]
scope = ["python/sadi/server/curve_source.py", "python/sadi/server/app.py", "python/tests/server/test_curve_source_open_session.py", "python/sadi/server/routes_stress_strain.py", "python/tests/server/test_curve_source.py", "python/tests/server/test_session_replay_cache.py", "python/tests/server/test_curve_notes_latency.py", "python/tests/server/test_routes_stress_strain.py"]

[[acceptance]]
text = "curve source takes open session path from SessionService; 409 no_open_session when none; test with two families where the open one does not sort last"
bound = false
+++
