+++
id = "01M6WEWKHPZ6NW5ZV7XDB1VK7J"
title = "Keep final-project material out of git: gitignore real_fp data, skip tests when absent, scrub doc and ticket mentions"
type = "task"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-08T02:13:07Z"
updated = "2026-11-08T02:17:19Z"
idempotency_key = "final-project-gitignore"
scope = [".gitignore", "python/tests/labs/lctt/test_real_data.py", "docs/lctt/slip.md", "docs/open-questions.md", "docs/plan.md", "docs/domain.md", "docs/preliminary-data-analysis.md", "changelog.d/01M6WE7E19D77NKF83TE5AM8Q6.changed.md", "docs/device/sim-faults.md", "docs/index.md", "docs/protocol.md", "docs/publishing.md", "python/pyproject.toml", "python/tests/fixtures/real_fp/**", "python/tests/labs/lctt/test_calibration.py"]

[[acceptance]]
text = "python/tests/fixtures/real_fp/ is untracked and gitignored; test_real_data.py skips cleanly when the data is absent"
bound = true

[[acceptance]]
text = "Tracked docs and tickets no longer name the reference VI, the course or the lab data path (generic wording instead)"
bound = true

[[acceptance]]
text = "A note records that git history still holds the old data and must be filtered before publishing"
bound = true
+++
