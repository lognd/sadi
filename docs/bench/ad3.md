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
| HANDLE_CLOSED | device handle already consumed (double close, use after close, lost device) |
| BAD_RESPONSE | garbage from the library: NaN/inf samples, short sample count, unknown state, non-ASCII or empty name/SN, absurd device count |
| SYMBOL_MISSING | the library lacks an FDwf function (old or wrong libdwf) |
| BAD_ARGUMENT | wrong type, NaN/inf, non-bool flag, unknown enum member; rejected before the FFI call |
| OUT_OF_RANGE | channel/node/index/count/mask outside its range (c_int/c_uint, buffer cap) |
| DEVICE_LOST | the device vanished mid-use; the handle is invalidated and unregistered |
| BUSY | device open in another process (erc ALREADY_OPENED or message) |
| TIMEOUT | API lock timeout (erc) or `wait_acquired` deadline |
| NOT_SUPPORTED | erc NOT_SUPPORTED |
| FFI_ERROR | `OSError` from the native call |
| UNEXPECTED | any other exception from the native call, contained |

No exception escapes `CtypesBackend`: it is a facade over the thin ctypes layer. Inputs are
validated before the FFI call, outputs after it, calls are serialized by an `RLock`, and every
error is logged on `sadi.bench.ad3.dll`. Erc mapping: 2 -> TIMEOUT, 3 -> BUSY, 4 ->
NOT_SUPPORTED, 0x10..0x14 -> BAD_ARGUMENT; otherwise message text (disconnect markers ->
DEVICE_LOST, in-use markers -> BUSY), else the call's default code.

Lifecycle: opened handles are registered; an `atexit` hook (`close_all_open`) closes leaked
ones with a warning. `wait_acquired(backend, dev, timeout_s)` is the bounded polling loop and
returns `Err(TIMEOUT)` rather than spinning forever. Enumeration reports `in_use` per device
when `FDwfEnumDeviceIsOpened` exists.

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

## Installing without apt

Use this when `apt install` of the WaveForms `.deb` fails (offline or
unreachable mirror, huge Qt/GUI dependencies). It mirrors the doctor remedy
`_deb_workaround_steps()` in `python/sadi/doctor/checks/ad3.py`.

1. Extract the package and point SADI at the library:

   ```sh
   dpkg-deb -x <path>/digilent.waveforms_*_amd64.deb ~/.local/share/digilent-waveforms
   export SADI_DWF_LIB=$HOME/.local/share/digilent-waveforms/usr/lib/libdwf.so
   ```

2. libdwf hardcodes `/usr/share/digilent/waveforms/firmware`, so copy it
   (needs sudo):

   ```sh
   sudo mkdir -p /usr/share/digilent
   sudo cp -r ~/.local/share/digilent-waveforms/usr/share/digilent/waveforms /usr/share/digilent/
   ```

   Without it, open fails with `Device not supported. No compatible
   configuration found`.
3. The Adept runtime must also be installed.
4. Your shell needs the `dialout` group: relogin, or run via
   `sg dialout -c '<command>'`.
5. Always close the device before the process exits.

## SADI wiring (`sadi.bench.inject.SADI_PINS`)

| AD3 | SADI | Polarity | Route |
|-----|------|----------|-------|
| W1 + GND | ACH0 +/- | positive | `lvdt` (out 0) |
| W2 + GND | ACH2 +/- | negative | `load` (out 1) |
| (none) | ACH1 | floating | unused |
| Scope ch 1 (index 0) | SADI GND and +3V3 | n/a | `supply_scope_channel` |

Source: the pin mapping is from the operator's wiring description and is
unverified on hardware. NOT verified on hardware:
the AD3 was not enumerated by WSL during this change (only the SADI serial
port was present), so no signal or supply voltage was measured.

See also: [LCTT test flow driven by the AD3](lctt-ad3-matrix.md).
