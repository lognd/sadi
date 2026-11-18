+++
id = "01M72ZNB9TN1CWMCK5G1J1H0BX"
title = "Sim LVDT voltage never moves on calibrate mark; SIM_LOAD_STEP_KG mismatches panel masses"
type = "bug"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T15:01:42Z"
updated = "2026-11-10T15:07:14Z"
labels = ["creates:python/tests/server/test_live_sim.py"]
scope = ["python/sadi/server/live.py", "python/tests/server/test_live_sim.py", "python/tests/server/test_live_load_change.py"]

[[acceptance]]
text = "Sim calibrate marks at different gauge blocks yield distinct volts so the calibration gate can pass"
bound = true

[[acceptance]]
text = "SIM_LOAD_STEP_KG matches the 0.075/1.05/2.325 kg masses the panel instructs"
bound = true
+++

Follow-up from ~5V612KT: only the message was fixed; the sim still cannot pass the cal gate (audit8 M5).
