+++
id = "01M726PZKE3CYNC5NABZC56HT2"
title = "H2: failed writer must spill undurable records on close/shutdown"
type = "bug"
category = "done"
outcome = "done"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T07:45:41Z"
updated = "2026-11-10T07:54:45Z"
labels = ["creates:python/tests/server/test_failed_writer_spill.py"]
scope = ["python/sadi/server/service.py", "python/sadi/store/spill.py", "python/tests/server/test_failed_writer_spill.py", "docs/data-safety.md", "python/sadi/store/writer_thread.py"]

[[acceptance]]
text = "When writer.close fails, undurable_records() are written to a spill segment (fsync file+dir) under data-root/spill, then user dir, then temp, path logged; close returns 409 if undurable records exist and spill failed; import_all_spills recovers them at next start; test with injected failed writer; docs updated. DATA SAFETY: AT NO POINT SHOULD WE BE ABLE TO LOSE ANY DATA"
bound = true
+++
