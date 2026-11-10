+++
id = "01M72T4QZQQABVKR5PX78KV8YS"
title = "Design selector: use recorded elastic/plastic phases, yield offset, single next-weight source, gauge wording"
type = "bug"
category = "todo"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T13:25:15Z"
updated = "2026-11-10T13:25:15Z"
labels = ["creates:none"]
scope = ["python/sadi/design/**", "python/sadi/server/routes/design.py", "python/tests/server/test_design_route.py", "python/tests/design/**", "web/src/screens/run/SuggestedWeightPanel.tsx", "web/src/screens/run/designAdvice.ts", "web/src/screens/run/SuggestedWeightPanel.test.tsx"]

[[acceptance]]
text = "Route maps ELASTIC->elastic, YIELD->plastic, LVDT_CAL->calibration; yield without elastic fit returns null suggestion with reason; test captures via POST points; Run screen shows one next-weight source; calibration panel says gauge height in mm"
bound = false
+++

Audit6 M1,M5,L3 in scratchpad audit6.md. design_obs filters phase=='load' but wizard records 'elastic'/'plastic'/'calibration'; yield never gets offset so suggests 0 kg; guidance line and SuggestedWeightPanel disagree; LVDT cal says weight/m.
