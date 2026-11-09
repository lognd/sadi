+++
id = "01M700HP4ZDWZ2AQ641TE0531N"
title = "Base CI red since d62d351cc: fix or revert the land range after (no green run)"
type = "bug"
category = "todo"
priority = "high"
reporter = "lognd"
created = "2026-11-09T11:19:24Z"
updated = "2026-11-09T11:19:24Z"
idempotency_key = "culprit-d62d351cc3aced40d8a0c075f1593dff53d61a3b"
labels = ["blocks-lands"]
+++

Base CI is red. Land commits between the last green run and the first red run:
- 15dcad4e3 tickets(land): ~VC7QQWM doctor: AD3 checks - libdwf in WSL, Windows-side dwf.dll/WaveForms via powershell.exe, attached-to-WSL vs Windows, WaveForms process holding device
- eebae8127 tickets(land): ~G0ZFJH3 doctor DEV-020: board does not answer on /dev/ttyUSB1; probe both FT2232 channels and framing
- c402ab238 tickets(land): ~BDQ2060 doctor AD3-020/040: when apt install of WaveForms fails, document extract-deb + copy /usr/share/digilent/waveforms firmware workaround
- ffe5da4af tickets(land): ~8AMGV5D AD3 dwf facade hardening: exhaustive edge cases, no exception escapes the CtypesBackend, Result everywhere
- 1a47172d2 tickets(land): ~Z37V6TP DAD parity with SADI: high-level typani device wrapper (typestate, context manager, Result, ErrorSet) plus full doctor family, launcher/docs integration
- 97b2ecc13 tickets(land): ~MHJSE85 FakeDwf supports only SINGLE acquisition: no continuous streaming for AD3 LCTT E2E
- 057d68258 tickets(land): ~QHPQMC1 doctor USB-070: step-by-step fix for FTDI latency_timer 16 -> 2 on WSL (udev/sysfs, read-only guidance plus fix --apply command)
- 138ab590b tickets(land): ~N220D8K doctor WEB-010/DATA-010: actionable setup steps (build UI bundle, create data root) and sadi doctor fix --apply entries
- dc0b1e4ba tickets(land): ~A6NSWK8 Migrate launcher.open_sim_device and doctor hostprobe/probes/checks/ext to devfacade (no raw sadi_py/pyserial)
- df2201cb6 tickets(land): ~MS8S7BG Launcher integration for the AD3 wrapper (open_ad3 via sadi launcher, closes device on exit)
- 58fd6ec9c tickets(land): ~84QQJAV Verify Ad3Guard SIGTERM/SIGHUP handlers coexist with uvicorn shutdown (restore prior handlers, close exactly once, test with subprocess)
- b610799e5 tickets(land): ~PZ6XTCC Investigate one-off 30s child-exit timeout in test_ad3_launch_signals SIGTERM subprocess test (not reproduced in ~30 reruns)
- 9cb853fa9 tickets(land): ~YK5K182 Audit Ad3Guard._on_signal/close for logging reentrancy: a signal during a logging stream write can raise RuntimeError (reentrant BufferedWriter) and skip the device close
- 7fcc74a30 tickets(land): ~QSSQKCZ Fix tests/core/test_phases.py::test_kind_mapping[codec]: phases.to_device_error maps codec to BAD_DATA but test expects PROTOCOL; reconcile with devfacade mapping
- e82b3421d tickets(land): ~RJWKZGZ Fix 9 eslint errors in web: e2e and docs-shots files not covered by tsconfig/project service
- 1b78bb8b1 tickets(land): ~4GF9WSA Flaky: test_sigterm_subprocess_single_close_exit_code fails in full pytest run, passes alone
- a27b8c4bf tickets(land): ~FZSTZCM doctor fix --apply: allow DATA-010 mkdir and WEB-010 build
