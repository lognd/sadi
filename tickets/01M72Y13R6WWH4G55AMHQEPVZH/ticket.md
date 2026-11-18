+++
id = "01M72Y13R6WWH4G55AMHQEPVZH"
title = "Enter L0 and hanger-mass uncertainty in the app (LabVIEW parity H1, M3)"
type = "story"
category = "todo"
priority = "high"
points = 3
reporter = "lognd"
created = "2026-11-10T14:33:10Z"
updated = "2026-11-10T14:33:10Z"
labels = ["creates:python/tests/labs/lctt/test_l0_input.py"]
scope = ["python/sadi/labs/lctt/lab.py", "python/sadi/labs/lctt/loading.py", "python/sadi/labs/lctt/export_csv.py", "web/src/screens/run/inputFields.ts", "python/sadi/core/point_inputs.py"]

[[acceptance]]
text = "Operator can type gauge length L0 and its uncertainty and hanger-mass uncertainty in the tare step; strain, E, U_strain and the CSV use them; defaults stay 0.5 and 0.08313 m when blank."
bound = false
+++

From parity audit scratchpad/parity.md gaps H1 and M3. L0 is hard-coded in loading.py:19-20; u_hanger_kg exists in SpecimenInputs but has no web field. Note lab.py has uncommitted tare edits on main; commit them first.
