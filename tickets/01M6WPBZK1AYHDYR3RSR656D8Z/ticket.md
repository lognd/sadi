+++
id = "01M6WPBZK1AYHDYR3RSR656D8Z"
title = "tests: isolate user data dir and OS temp dir in tests/server so startup spill import never scans real dirs"
type = "bug"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T04:23:51Z"
updated = "2026-11-08T04:25:06Z"
scope = ["python/tests/conftest.py", "python/tests/server/conftest.py", "python/tests/cli/conftest.py", "python/tests/cli/test_launcher_spill.py", "python/tests/server/test_spill_isolation.py"]

[[acceptance]]
text = "Autouse fixture in tests/server and tests/cli conftest redirects user data dir and OS temp dir"
bound = true

[[acceptance]]
text = "A test shows create_app startup in tests/server does not see a spill outside the isolated dirs"
bound = false
+++

import_all_spills scans the user data dir and the OS temp dir at app startup. The new tests in python/tests/cli/test_launcher_spill.py redirect both to empty temp dirs, but the other tests/server tests do not and so scan the real ones (nondeterministic, and could import a real spill during a test). Add an autouse fixture in python/tests/server/conftest.py (and tests/cli if missing) that redirects both locations. Acceptance: autouse fixture exists; a test plants a spill file in the real-dir stand-in and asserts create_app startup in tests/server does not see it.
