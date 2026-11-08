+++
id = "01M6WMZHNS2E0QNW7KFZ1GAYMZ"
title = "doctor: mark catalog commands fixable (udev, usbipd attach, browser open) so fix --apply has work"
type = "task"
category = "in-progress"
priority = "medium"
points = 2
reporter = "lognd"
created = "2026-11-08T03:59:35Z"
updated = "2026-11-08T04:05:46Z"
labels = ["doctor"]
scope = ["python/sadi/doctor/checks/usb.py", "python/sadi/doctor/checks/brw.py"]
+++

From ~GAG48CQ: no catalog command is tagged fixable, so 'sadi doctor fix --apply' reports nothing to do. Tag the safe system/process commands from doc 4.4.
