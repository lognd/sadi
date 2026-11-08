# Run screens: usability notes

Status: current

Part of the [usability report](../../../../docs/usability-report.md) (~W5XJBZT).

- Tab order: inputs, Accept/Record, Mark load change, Finish, Skip, Doctor. Focus rings present.
- U-01 (sev 1, ticketed ~0MZ866N): Enter or Space on a focused button fires the global hotkey, not the button.
- U-04 (sev 2): hotkeys are ignored in inputs; tell the operator to Tab off the field first.
- U-05 (sev 2, fixed ~81EQRYA): phase text and a hint beside Mark load change say it is required before Settled.
- U-06 (sev 2): zero-point finish advances with an unclear device_fault message.
- Timing: about 10 s per point is detector settle time; the UI adds none.
