+++
id = "01M6WN9ZE5EHGWZZ58M973FKGT"
title = "Audit StrEnum error families in doctor/** and server/** -> typani ErrorSet (doctor/schema.py DoctorError etc)"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T04:05:17Z"
updated = "2026-11-08T04:08:53Z"
labels = ["python"]
scope = ["docs/doctor.md", "creates:python/tests/doctor/test_error_families.py", "python/tests/doctor/test_error_families.py"]

[[acceptance]]
text = "Doctor and server error families are typani ErrorSets; label/status enums stay StrEnum with unchanged wire values"
bound = true
+++

From ~PYEFC79: core/store done; doctor and server were out of its lease. Convert error enums only; keep state/label enums; preserve wire values; record per-enum decision.
