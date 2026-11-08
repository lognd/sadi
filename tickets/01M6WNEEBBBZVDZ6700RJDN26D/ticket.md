+++
id = "01M6WNEEBBBZVDZ6700RJDN26D"
title = "lctt capture: record averaged-volts POINTs via AcquisitionDriver.record_point"
type = "task"
category = "todo"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T04:07:43Z"
updated = "2026-11-08T04:07:43Z"
labels = ["python"]
+++

HNRCGB7 added record_point and the shared phase mapping, but labs/lctt/capture.py still builds POINTs from mode and window only. Capture has no averaged-volts value to record. Wire capture to produce LoadInputs (volts, mass_kg, optional uncertainties) and call record_point. Acceptance: a capture run yields WAL POINT events that recover_state and the curve source replay.
