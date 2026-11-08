+++
id = "01M6WNEEBBBZVDZ6700RJDN26D"
title = "lctt capture: record averaged-volts POINTs via AcquisitionDriver.record_point"
type = "task"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T04:07:43Z"
updated = "2026-11-08T04:11:01Z"
labels = ["python"]
scope = ["python/sadi/labs/lctt/capture.py", "python/tests/labs/lctt/test_capture.py", "docs/lctt/capture.md", "creates:python/tests/labs/lctt/test_capture_record.py", "python/tests/labs/lctt/test_capture_record.py"]

[[acceptance]]
text = "Captured points carry LoadInputs with window-averaged volts and the start_point mass"
bound = false

[[acceptance]]
text = "A capture run recorded via record_point replays through recover_state and the curve source"
bound = false
+++

HNRCGB7 added record_point and the shared phase mapping, but labs/lctt/capture.py still builds POINTs from mode and window only. Capture has no averaged-volts value to record. Wire capture to produce LoadInputs (volts, mass_kg, optional uncertainties) and call record_point. Acceptance: a capture run yields WAL POINT events that recover_state and the curve source replay.
