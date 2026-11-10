+++
id = "01M72D3CTDED2MGDY721RSM8M4"
title = "Audit5: wizard override_input validation, doctor re-run probe, CSV uncertainty model, phase-split curves, download names, export CSRF guard"
type = "bug"
category = "todo"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-10T09:37:19Z"
updated = "2026-11-10T09:37:41Z"
labels = ["creates:python/tests/server/test_export_guard_names.py", "creates:python/tests/core/test_wizard_edit_validation.py"]
scope = ["python/sadi/core/wizard.py", "python/sadi/server/routes_doctor.py", "python/sadi/labs/lctt/export_csv.py", "python/sadi/labs/lctt/figure_data.py", "python/sadi/server/curve_source.py", "python/sadi/server/security.py", "python/sadi/server/routes/export.py", "python/tests/core/test_wizard.py", "web/src/screens/export/**", "web/src/state/provenance.ts", "docs/lctt/export-csv.md", "docs/server/**", "web/src/api/openapi.json", "web/src/api/schema.ts", "changelog.d/**", "python/tests/labs/lctt/test_export_csv.py", "python/tests/labs/lctt/test_export_csv_phases.py", "python/tests/labs/lctt/test_lab_export.py", "python/tests/server/test_curve_source.py", "python/tests/server/test_export_routes.py", "python/tests/server/test_origin_guard.py", "python/tests/server/test_routes_doctor.py", "python/tests/server/test_openapi_export.py", "python/tests/server/test_export_guard_names.py", "python/tests/core/test_wizard_edit_validation.py"]

[[acceptance]]
text = "Wizard.edit override_input merges over current inputs, re-runs parse_inputs+check_ranges, rejects unknown keys/phase/NaN/strings with an error and stores nothing"
bound = false

[[acceptance]]
text = "Doctor POST re-run passes probe_device=False"
bound = false

[[acceptance]]
text = "CSV row uses one uncertainty model for u_strain and u_displacement_m, documented in metadata and docs, with a consistency test"
bound = false

[[acceptance]]
text = "StressStrainData has phase; figure splits elastic/plastic series; load_session_curve fits elastic rows only"
bound = false

[[acceptance]]
text = "Downloads use server Content-Disposition name when X-SADI-Provenance present (no double SYNTHETIC- prefix)"
bound = false

[[acceptance]]
text = "OriginGuard refuses Sec-Fetch-Site cross-site GET on /api/export/* with tests"
bound = false
+++

Audit5 findings L3 L4 L5 L6 and M6 MED 1 / MED 5. Data-safety mandate: no data loss; atomic, recoverable, never auto-overwritten.
