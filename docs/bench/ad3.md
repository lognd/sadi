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
