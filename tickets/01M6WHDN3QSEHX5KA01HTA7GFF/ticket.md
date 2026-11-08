+++
id = "01M6WHDN3QSEHX5KA01HTA7GFF"
title = "plugins CLI: show doctor findings in info and add console script"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T02:57:23Z"
updated = "2026-11-08T02:59:35Z"
scope = ["python/pyproject.toml", "python/tests/cli/**", "python/uv.lock"]
+++

sadi plugins info should include check_plugins() findings with numbered fix steps (python/sadi/plugins/doctor.py). Add a console script entry in python/pyproject.toml so it runs without python -m. Keep LocalDirSource import behaviour.
