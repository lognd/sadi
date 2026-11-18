# Run screens: usability notes

Status: current

Part of the [usability report](../../../../docs/usability-report.md) (~W5XJBZT).

- Tab order: inputs, Accept/Record, Mark load change, Finish, Skip, Doctor. Focus rings present.
- U-01 (sev 1, ticketed ~0MZ866N): Enter or Space on a focused button fires the global hotkey, not the button.
- U-04 (sev 2, fixed ~RD34EXF): hotkeys are ignored in inputs; a hint under the inputs says so and Esc or Tab returns to them (Esc blurs the field).
- U-05 (sev 2, fixed ~81EQRYA): phase text and a hint beside Mark load change say it is required before Settled.
- U-06 (sev 2, fixed ~BJVWSNR): a stop shows plain language plus what to do (check cable, open Doctor); with zero points it also says to capture a point first.
- Timing: about 10 s per point is detector settle time; the UI adds none.

## Device fault

After a `device_fault` stop the status bar and live readout show "Faulted" (never "Connected"), a fault notice is shown and capture is blocked until the next stream hello. The server `simulated` flag follows `DeviceService.is_simulator`, so it survives a fault.
