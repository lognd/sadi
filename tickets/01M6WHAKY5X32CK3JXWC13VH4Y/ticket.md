+++
id = "01M6WHAKY5X32CK3JXWC13VH4Y"
title = "Deduplicate SessionPluginRef (store.manifest vs plugins.doctor)"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T02:55:44Z"
updated = "2026-11-08T02:56:51Z"
scope = ["python/sadi/plugins/doctor.py", "python/tests/plugins/test_doctor.py"]
+++

Two identical SessionPluginRef models exist: python/sadi/store/manifest.py and python/sadi/plugins/doctor.py. Keep one canonical definition (store must not import plugins, so doctor should import from the store manifest or a shared core module) and update tests.
