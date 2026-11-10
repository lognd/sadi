+++
id = "01M72D3CTDED2MGDY721RSM8M4"
title = "Audit5: wizard override_input validation, doctor re-run probe, CSV uncertainty model, phase-split curves, download names, export CSRF guard"
type = "bug"
category = "todo"
priority = "medium"
points = 5
reporter = "lognd"
created = "2026-11-10T09:37:19Z"
updated = "2026-11-10T09:37:19Z"
scope = ["python/sadi/core/wizard.py", "python/sadi/server/routes_doctor.py", "python/sadi/labs/lctt/export_csv.py", "python/sadi/labs/lctt/figure_data.py", "python/sadi/server/curve_source.py", "python/sadi/server/security.py", "python/sadi/server/routes/export.py", "python/tests/core/test_wizard.py", "python/tests/labs/lctt/**", "python/tests/server/**", "python/tests/doctor/**", "web/src/screens/export/**", "web/src/state/provenance.ts", "docs/lctt/export-csv.md", "docs/server/**", "web/src/api/openapi.json", "web/src/api/schema.ts", "changelog.d/**"]

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
