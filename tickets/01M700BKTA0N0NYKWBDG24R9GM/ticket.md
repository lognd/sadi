+++
id = "01M700BKTA0N0NYKWBDG24R9GM"
title = "ci: crash tests fail on Windows (I4 snapshot changed, locked lock file in copytree)"
type = "bug"
category = "done"
outcome = "done"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-09T11:16:08Z"
updated = "2026-11-09T11:26:24Z"
scope = ["python/tests/crash/**"]

[[acceptance]]
text = "given the crash suite, when run on Windows, then oracle digests match and the held lock file does not break clone or digest"
bound = true
+++
