+++
id = "01M6WPW00ACPBJY4XD54ZPY9YT"
title = "Replace remaining StrEnum error families in doctor/ and server/ with typani ErrorSet"
type = "task"
category = "in-progress"
priority = "low"
points = 2
reporter = "lognd"
created = "2026-11-08T04:32:36Z"
updated = "2026-11-08T04:33:16Z"
+++

Follow-up from PYEFC79: StrEnum uses in python/sadi/doctor (schema.py) and python/sadi/server were skipped due to leases. Convert error families to typani ErrorSet; leave non-error StrEnums.
