# AD3 Digilent DWF binding

Status: current

Verification: Linux/WSL path is untested against hardware; Windows and macOS are UNVERIFIED without hardware.

Package `sadi.bench.ad3` is a typed binding to the Digilent WaveForms runtime
(`libdwf`). `dll.py` is the only module that touches `ctypes`; everything else
depends on the device-agnostic `DwfBackend` Protocol in `backend.py`, which a
fake implementation can satisfy. Constants are transcribed from the vendor
`dwf.h` (needed subset only; header, DLL and samples are not vendored).

## Library discovery

Importing the package never loads a library. `load_backend()` tries, in order:
the `SADI_DWF_LIB` environment variable, then the per-OS names below.

| OS | Names tried | Install | Status |
|----|-------------|---------|--------|
| Linux | `libdwf.so`, `/usr/lib/libdwf.so`, `/usr/lib/digilent/waveforms/libdwf.so` | WaveForms + Adept runtime | untested without hardware |
| Linux under WSL | as Linux | as Linux, plus `usbipd list/bind/attach` on the Windows host | untested without hardware |
| Windows | `dwf.dll`, `C:\Windows\System32\dwf.dll`, `ctypes.util` result | WaveForms installer (no usbipd) | UNVERIFIED |
| macOS | `/Library/Frameworks/dwf.framework/dwf`, `dwf.framework/dwf` | WaveForms dmg | UNVERIFIED |

WSL is detected by `microsoft` in `/proc/version`; usbipd steps appear only there.
A missing library returns `Err(DwfError(LIBRARY_MISSING))` whose `hint` is a
numbered, per-OS fix list.

## Doctor checks (AD3-nnn)

`sadi doctor` (layer `ad3`) checks the AD3 on whichever side runs it; every
headline is tagged `[linux]`, `[wsl]` or `[windows]`. All checks are read-only.

| Check | linux | wsl | windows |
|-------|-------|-----|---------|
| AD3-010 visible (VID 1443, PID 7003) | sysfs | sysfs, else Windows PnP via `powershell.exe` (WARN: held by Windows) | `Get-PnpDevice` |
| AD3-020 runtime library | `libdwf.so` (same names as above) | `libdwf.so`; if absent but `/mnt/c/Windows/System32/dwf.dll` exists, headline fix is `usbipd.exe detach --busid <id>` and use Windows `python.exe` (alternative: install the Linux packages) | `C:\Windows\System32\dwf.dll` |
| AD3-030 WaveForms/Adept process | `pgrep` | `Get-Process` via `powershell.exe` | `Get-Process` |
| AD3-040 open via backend (`--ad3-open`) | child process | child process | child process |

Without `powershell.exe` under WSL (interop off) the Windows-side checks SKIP
with a reason. With no AD3 present, checks SKIP (NO_DEVICE).

## Errors

All fallible calls return typani `Result[T, DwfError]`.

| Code | Meaning |
|------|---------|
| LIBRARY_MISSING | no candidate loaded; see numbered hint |
| DEVICE_NOT_FOUND | open failed or returned no handle |
| CALL_FAILED | DWF returned 0; detail carries `FDwfGetLastErrorMsg` and erc |
| HANDLE_CLOSED | device handle already consumed |
| BAD_RESPONSE | unrecognised value from the library |

DWF returns BOOL where 0 is failure (the ticket text says "nonzero"; the real API is used).

## Typestate

`backend.open()` yields an `OpenDevice`; `backend.close(dev)` consumes it and
returns a `ClosedDevice` that has no operations. Reusing a consumed handle
returns `Err(HANDLE_CLOSED)` without calling the library.

## Usage

```python
from sadi.bench.ad3 import load_backend
be = load_backend().unwrap()
dev = be.open(-1).unwrap()
```
