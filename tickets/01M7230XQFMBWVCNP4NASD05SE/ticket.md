+++
id = "01M7230XQFMBWVCNP4NASD05SE"
title = "Audit2 H6: excluded calibration/tare/specimen points still used by CSV export and calibration plot"
type = "bug"
category = "todo"
priority = "high"
points = 2
reporter = "lognd"
created = "2026-11-10T06:41:12Z"
updated = "2026-11-10T06:41:12Z"
scope = ["python/sadi/server/curve_source.py", "python/sadi/server/routes/plots.py", "python/sadi/server/routes/export.py", "python/tests/server/__pycache__", "python/tests/server/conftest.py", "python/tests/server/test_action_latency.py", "python/tests/server/test_app.py", "python/tests/server/test_clamp_route.py", "python/tests/server/test_curve_flags.py", "python/tests/server/test_curve_notes_latency.py", "python/tests/server/test_curve_source.py", "python/tests/server/test_export_routes.py", "python/tests/server/test_inventory_routes.py", "python/tests/server/test_loop_lag.py", "python/tests/server/test_openapi_export.py", "python/tests/server/test_plots_routes.py", "python/tests/server/test_results_routes.py", "python/tests/server/test_results_stream.py", "python/tests/server/test_resume_fold.py", "python/tests/server/test_routes.py", "python/tests/server/test_routes_acquisition.py", "python/tests/server/test_routes_doctor.py", "python/tests/server/test_routes_health.py", "python/tests/server/test_routes_plugins.py", "python/tests/server/test_routes_problem.py", "python/tests/server/test_routes_stress_strain.py", "python/tests/server/test_run_phase.py", "python/tests/server/test_save_indicator.py", "python/tests/server/test_save_wired_and_sim_provenance.py", "python/tests/server/test_service_revert.py", "python/tests/server/test_service_snapshots.py", "python/tests/server/test_session_points.py", "python/tests/server/test_session_replay_cache.py", "python/tests/server/test_spill_isolation.py", "python/tests/server/test_ws.py", "python/tests/server/test_ws_results.py"]

[[acceptance]]
text = "session_events honours exclusions for all point kinds; test: excluding a cal point changes CSV slope and plot fit"
bound = false
+++
