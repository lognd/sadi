+++
id = "01M72D7HV896669TN0TZCAYZK3"
title = "Spill join renumbers seqs after SEAL records (raw-seq refs shift)"
type = "bug"
category = "todo"
priority = "low"
reporter = "lognd"
created = "2026-11-10T09:39:35Z"
updated = "2026-11-10T09:39:35Z"
scope = ["python/sadi/store/spill.py", "python/tests/store/test_spill.py"]

[[acceptance]]
text = "joined WAL keeps original seqs or manifest records an offset map"
bound = false
+++

found while working PXPD3AB (audit5 L2): joined spill WAL drops SEALs and renumbers densely; POINT first_raw_seq/last_raw_seq and MARKER raw_seq keep parent numbering. Keeping original seqs needs multi-segment output with valid SEAL frames (walker treats SEAL as segment end) or a manifest seq offset map. Only affects parents that rotated.
