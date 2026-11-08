+++
id = "01M6WE7E19D77NKF83TE5AM8Q6"
title = "Validate calibration fit and slip detector against real local lab data data"
type = "task"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T02:01:33Z"
updated = "2026-11-08T02:03:29Z"
scope = ["python/tests/fixtures/real_fp/**", "python/tests/labs/lctt/test_real_data.py", "docs/lctt/slip.md"]

[[acceptance]]
text = "fit_calibration reproduces the VI slope, intercept, se and t95 on the 12 real points within 1e-6 relative"
bound = true

[[acceptance]]
text = "detect_slip is run on the real the local short-run file time series and the result is documented in docs/lctt/slip.md"
bound = true
+++

Use local lab data/lvdt_calibration.txt (12 points; VI reports slope 2.114583E-3 m/V, intercept 2.472866E-2 m, se slope 6.734580E-6, t95 2.228139, n 12) to check fit_calibration agrees with the VI. Use the local short-run data file (CRLF, header block, then time series) to run detect_slip. Do not commit the raw files if large or private: copy a trimmed fixture under python/tests/fixtures/. Parser must treat the file as read-only.
