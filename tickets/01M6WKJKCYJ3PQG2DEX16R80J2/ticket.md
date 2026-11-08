+++
id = "01M6WKJKCYJ3PQG2DEX16R80J2"
title = "Server doctor endpoints: GET /api/doctor and POST /api/doctor/{check_id}/run"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T03:35:02Z"
updated = "2026-11-08T03:36:03Z"
scope = ["python/sadi/server/routes_doctor.py", "python/tests/server/test_routes_doctor.py"]

[[links]]
kind = "blocked-by"
target = "01M6WA9WZW89EA826DSJCJ0197"

[[acceptance]]
text = "GET /api/doctor returns a DoctorReport"
bound = false

[[acceptance]]
text = "POST /api/doctor/{check_id}/run re-runs one check and returns its CheckResult"
bound = false
+++

Follow-up from JCJ0197: implement the endpoints the web doctor client expects (DoctorReport / CheckResult from python/sadi/doctor/schema.py); see docs/web/doctor-ui.md.
