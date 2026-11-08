# Portability audit

Status: current

Owner: ticket ~PVJNZ7V. Scope: Windows, Linux (incl. WSL2) and macOS. The wire
protocol and all FTDI behaviour below are UNVERIFIED until a hardware session
([protocol.md](protocol.md) section 10, [hardware-verification.md](hardware-verification.md));
nothing is hard-coded and baud and port are configuration.

## 1. Serial port naming

| OS | VCP name | Notes |
|---|---|---|
| Windows | `COM3`, `COM12` | Ports above `COM9` need the `\\.\COM12` form for raw Win32; the `serialport` crate adds the prefix itself. The number can change per USB port and per FTDI serial number. |
| Linux | `/dev/ttyUSB0..N` | The FT2232H/FT4232H exposes one node per channel; order is enumeration order, not stable. Prefer `/dev/serial/by-id/usb-FTDI_*-ifNN-port0`. |
| macOS | `/dev/cu.usbserial-<serial>`, `/dev/tty.usbserial-*` | Open the `cu.*` node (no carrier wait); `tty.*` blocks on DCD. Channel suffix `A`/`B` appended on multi-channel parts. |

Code: `crates/sadi-proto/src/serial.rs` `list_ports` selects by USB VID/PID
(`FTDI_ALLOW_LIST`: 0403:6010, 0403:6014, 0403:6001), not by name, so the
name pattern never needs to be guessed; an explicit port name is only the
override. Multi-channel parts: the board's channel (A or B) must be chosen by
interface/product string, which is unverified.

## 2. FTDI drivers: VCP vs D2XX

The crate uses the VCP (OS serial) path only. D2XX (proprietary libftd2xx) and
VCP are mutually exclusive per device: a device claimed by one is not visible
to the other.

- Windows: the FTDI CDM package installs both a bus driver (`ftdibus.sys`, D2XX)
  and `ftser2k.sys` (VCP). Windows Update normally installs VCP. If "Load VCP"
  is unchecked in the device properties the COM port disappears; tick it and
  replug. Vendor tools (FT_Prog, LabVIEW VISA/D2XX) can hold the device open.
- Linux: the in-kernel `ftdi_sio` binds VCP. Using libftdi/D2XX requires
  unbinding `ftdi_sio` (`echo <busid> > /sys/bus/usb/drivers/ftdi_sio/unbind`) or
  blacklisting it; do not do this for SADI.
- macOS: Apple's built-in FTDI driver (10.9+) provides VCP. A legacy FTDI
  kext installed for the old LabVIEW setup conflicts; remove it. D2XX users
  can detach with `libftdi` but SADI must not be run at the same time.
- The old LabVIEW VI uses the vendor VISA/D2XX path: close it before running SADI.

## 3. WSL2 USB passthrough (usbipd)

WSL2 has no native USB. Either run the whole app on the Windows side (preferred
for the lab), or attach the device with `usbipd-win`:

```
usbipd list
usbipd bind --busid 2-3        (once, admin)
usbipd attach --wsl --busid 2-3
```

Then inside WSL the device appears as `/dev/ttyUSB0` provided the WSL kernel
has `ftdi_sio` (the stock Microsoft kernel may lack it; a custom kernel or
`modprobe ftdi_sio` is needed, unverified here). While attached, Windows loses
the device (no COM port). Apply `packaging/udev/99-sadi.rules` inside the
distro (WSL needs systemd udev or `sudo chmod 666 /dev/ttyUSB0`). Latency over
usbip is higher; timeouts tuned on native hardware may not hold.

## 4. Linux permissions (udev)

`packaging/udev/99-sadi.rules` grants group `dialout` (mode 0660) and the
`uaccess` tag to FTDI 0403:6010 and 0403:6014, and also 0403:6001 (FT232R,
matching the code allow-list), on both tty and raw usb nodes. The whole file
is UNVERIFIED; in particular the 0403:6001 lines were added speculatively, as
no FT232R part is confirmed on the board. Checklist rows 12-16 in
[hardware-verification.md](hardware-verification.md) track the rules (row 12),
the 0403:6001 lines (row 16), `by-id` naming (13), channel selection (14) and
WSL `ftdi_sio` (15). Some distros use `uucp` (Arch) or
`plugdev` instead of `dialout`; edit GROUP accordingly. ModemManager may probe
and briefly hold new ttys; add `ENV{ID_MM_DEVICE_IGNORE}="1"` if it interferes
(not applied: unverified).

## 5. Paths: Windows reserved names and long paths

- Reserved device names (`CON PRN AUX NUL COM1-9 LPT1-9`, with or without an
  extension) cannot be file names on Windows. Any name derived from user input
  (specimen id, session title) must be sanitised or use a generated id; trailing
  dots and spaces are also stripped by Win32. Forbidden characters: `<>:"/\|?*`.
- Path length: 260 chars (MAX_PATH) unless long paths are enabled in the OS and
  the process manifest. Keep data paths short (session directories use fixed
  ids, WAL segments fixed-width names); do not nest user-named folders deeply.
  Python 3.6+ honours long paths only when the registry opt-in is set.
- Case: NTFS and default macOS volumes are case-insensitive; Linux is not. Never
  rely on case to distinguish two files.
- Code uses `pathlib.Path` throughout (`python/sadi/store/*.py`); no hard-coded
  separators found. User-derived name sanitisation is centralised in
  `python/sadi/store/names.py` ([store/names.md](store/names.md)).

## 6. Durability: fsync, directory flush, locks

Implemented in `python/sadi/store/durable.py` ([store/durable.md](store/durable.md)):

- File flush: `os.fsync` (Windows `FlushFileBuffers`); macOS uses `F_FULLFSYNC`
  with a logged fallback (`durability_downgraded()`).
- Directory flush: real `fsync` on a directory fd on Linux and macOS; a documented
  no-op on Windows (cannot open a directory via `os.open`; NTFS journals metadata).
  Replace uses `MoveFileExW` with `WRITE_THROUGH` on Windows.
- Locks: each session directory takes a process-scoped exclusive OS lock
  (`fcntl.flock` on POSIX, `msvcrt.locking` on Windows) in
  `python/sadi/store/session.py` (`_try_os_lock`), so a second process opening
  the same session is refused. Windows and macOS behaviour is UNVERIFIED.
  There is no lock at data-root level yet (~X8YD1SA). `flock` is
  per-open-file-description on Linux and Windows locks are mandatory, so the
  lock stays wrapped in that one module.
- Network and exFAT/FAT volumes may ignore or downgrade flushes; see data-safety.md.

## 7. Antivirus and sharing violations

Windows real-time scanners and the search indexer open freshly written files
and cause `ERROR_ACCESS_DENIED` (5) or `ERROR_SHARING_VIOLATION` (32) on rename
or create. `durable.py` retries these with capped exponential backoff (about 5 s
total) and then returns `DurableSharingViolation` with a hint to exclude the data
folder from scanning. Recommend excluding the data directory in the lab setup
guide. Linux and macOS do not exhibit this.

## 8. Line endings and CSV

- The legacy VI output is a 32-column CSV; Excel on Windows expects CRLF and
  may expect a UTF-8 BOM for non-ASCII text (units such as the micro sign).
- Rule: write export CSV with explicit `newline=""` and `encoding="utf-8"` (or
  `utf-8-sig` for Excel) and a fixed `\r\n` row terminator (the Python `csv`
  module default) on every OS, so output is byte-identical across platforms.
  When reading, use `newline=""` so embedded newlines and CRLF both parse.
- Binary stores (WAL, segments) must be opened in binary mode; `durable.py`
  already adds `O_BINARY` for Windows. Text-mode opens translate `\n` on
  Windows and would corrupt checksums.
- Implemented (~K79AJH0): `python/sadi/store/csv_export.py` renders the bytes in memory
  and writes them exclusively ([store/csv-export.md](store/csv-export.md)); `.gitattributes`
  carries `* text=auto`, `*.csv -text` and `*.json text eol=lf`.
- Web: downloads go through the browser, so the OS does not alter bytes; the
  CSV bytes are produced by the server and must follow the rule above.

## 9. Findings for follow-up

1. Centralise filename sanitisation (reserved names, forbidden characters, length).
2. Data-root lock to detect two SADI processes: ticket ~X8YD1SA (the per-session lock already exists).
3. Done (~K79AJH0): `.gitattributes` text/eol rules and a CSV export CRLF byte test.
4. Verify udev rules (including the 0403:6001 lines), `by-id` naming, channel
   selection and WSL `ftdi_sio` on hardware: tracked as rows 12-16 of
   [hardware-verification.md](hardware-verification.md), all pending and
   UNVERIFIED.
