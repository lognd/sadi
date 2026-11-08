+++
id = "01M6WV1BH9CPYGP6BP9VZ2YBEW"
title = "Wire a real DeviceService into launcher/app for /api/device/status"
type = "bug"
category = "in-progress"
priority = "medium"
points = 3
reporter = "lognd"
created = "2026-11-08T05:45:26Z"
updated = "2026-11-08T06:14:29Z"
scope = ["python/sadi/server/**"]

[[acceptance]]
text = "Launcher --sim passes the simulator DeviceService as AppSettings.device and closes it on shutdown"
bound = false

[[acceptance]]
text = "Without a device the launcher injects none, so status stays honestly unattached"
bound = false

[[acceptance]]
text = "A failing simulator open exits EXIT_DEVICE without serving"
bound = false
+++

found while working ~J73KJ11: AppSettings.device is never set, so status reports unattached
