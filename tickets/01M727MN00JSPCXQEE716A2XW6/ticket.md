+++
id = "01M727MN00JSPCXQEE716A2XW6"
title = "Fix test_point_roundtrip 409 NoOpenSession after open_session change (H3 regression)"
type = "bug"
category = "todo"
priority = "medium"
reporter = "lognd"
created = "2026-11-10T08:01:53Z"
updated = "2026-11-10T08:01:53Z"
scope = ["python/tests/api/test_point_roundtrip.py"]

[[acceptance]]
text = "python/tests/api/test_point_roundtrip.py::test_record_recover_fit_round_trip passes by opening a session in the test setup, without weakening the NoOpenSession guard"
bound = false
+++
