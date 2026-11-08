# sadi doctor: check catalog and step-by-step remediation

Status: current

Owner ticket: ~JPRPASC (design document, no code). Implementing tickets:
~V3H5CGF (check runner, checks, remediation, CLI; `python/sadi/doctor/**`,
`python/tests/doctor/**`, generated `docs/doctor-checks.md`) and ~JCJ0197
(Doctor screen in the web app). Each implements the section that names it,
exactly as written; a deviation is a change to this file in the same ticket,
not a silent divergence.

The user's requirement, verbatim:

> a doctor that checks EVERYTHING and instructs the user STEP-BY-STEP on how
> to fix things.

The audience is a first-time lab user (a student) on Windows, Linux, macOS or
WSL2 with usbipd, who has never opened a terminal. Every remediation is
therefore a numbered list of exact copy-paste commands for the OS the doctor
detected, each with the output the user should see, ending in a verify step
that re-runs the failing check. Facts this document relies on are owned by
[portability.md](portability.md) (ports, drivers, udev, usbipd, paths),
[hardware-verification.md](hardware-verification.md) (what is unverified on
the board), [data-safety.md](data-safety.md) (sessions, WAL, locks,
durability, per-OS filesystem table), [store/session.md](store/session.md),
[store/wal.md](store/wal.md), [concurrency.md](concurrency.md) (worker pool,
thread names), [device/session.md](device/session.md) (connect sequence and
timeouts), [device/simulator.md](device/simulator.md) and
[ux.md](ux.md) (error style, status model). They are cited, not restated.

## 0. Contents

1. Principles
2. Vocabulary: check, layer, severity, status, failure mode, remediation
3. Check catalog (acceptance 1)
4. Remediation format and mutation policy (acceptance 2)
5. Worked remediations (one per OS family)
6. Result schema: pydantic models (acceptance 3)
7. CLI: text and JSON
8. UI Doctor screen
9. Runner: plan, dependencies, timeouts, read-only enforcement, logging
10. Test strategy: fixtures and fault injection (acceptance 3)
11. Ticket split and follow-ups
12. Decisions

## 1. Principles

1. Read-only by default. `sadi doctor` opens files read-only, never creates,
   renames, truncates or deletes anything under the data root, never takes a
   session lock, never writes a WAL record and never changes OS state
   (data-safety.md I4, I8). The only writes a plain run performs are to its
   own log and, when `--bundle <path>` is given, to the path the user named
   outside the data root. Section 9.5 says how this is enforced and tested.
2. Fixes happen only on explicit user action, one at a time, after the doctor
   has printed exactly what it will do and the user has confirmed
   (section 4.4). No fix ever touches session data: data operations (resume,
   spill import) are app actions, the doctor only points at them.
3. Everything is checked. The catalog in section 3 is the definition of
   "everything"; a new subsystem adds a check in the same ticket (the
   documentation rule in docs/README.md applies). A check that cannot run
   reports `skip` with a reason, never silence.
4. Every failure says what to do. A `fail` or `warn` without a remediation is
   a programmer bug and is rejected by the schema (section 6).
5. Plain language first, technical detail second (ux.md section 6): the
   title states the situation, the first step starts with a verb, evidence
   and raw errors live under "Details".
6. One source of truth. The check registry in code generates
   `docs/doctor-checks.md`, the JSON schema, the UI's static strings and the
   catalog test matrix; a test asserts the generated doc is checked in and
   current (section 10.4).
7. Logged everywhere. Every probe call, its duration, result and every branch
   that selects a failure mode is logged through
   `sadi.logging_setup.get_logger(__name__)`; `print` is forbidden
   (python-layout.md).

## 2. Vocabulary

| Term | Meaning |
|---|---|
| Check | One question with a yes/no/degraded answer and a stable id, e.g. `USB-020 FTDI device visible to the OS`. |
| Layer | The subsystem a check belongs to; checks run in layer order so a lower failure can `skip` dependents (section 9.2). |
| Severity | How bad a `fail` of this check is for the user: `blocker` (SADI cannot start or cannot save data), `error` (a feature is unavailable: no real device, no workers), `warning` (degraded, can continue), `info` (advice). Severity is a property of the check, not of the run. |
| Status | Outcome of one run of a check: `pass`, `warn`, `fail`, `skip`. `warn` is a `fail` of a `warning`/`info` check or a soft condition of a stricter check (each check lists which). `skip` always carries a `skip_reason`. |
| Detection | The probes a check performs (file reads, OS queries, subprocess calls with fixed arguments, a protocol exchange) and the rule that turns their results into a status. |
| Failure mode | One distinguishable cause, written `CHECK-ID/mode`, e.g. `USB-020/no-device`, `USB-020/wrong-driver`. Each mode has exactly one remediation per OS. Distinguishing modes is the point of the doctor: "no COM port" and "COM port held by LabVIEW" need different steps. |
| Evidence | What the check saw, typed (section 6): paths, versions, device lists, byte counts, command output. Shown under "Details" and in JSON. |
| Remediation | Ordered steps for the detected OS, each with a command (or a manual action), expected output and a mutation class; always ending in a verify step (section 4). |
| OS | `windows`, `linux`, `macos`, `wsl`. WSL is a distinct OS for the doctor because its fixes differ (usbipd on the Windows side, kernel modules inside). Detection: `platform.system()`, then on Linux `WSL_DISTRO_NAME` in the environment or `microsoft` in `/proc/version` (case-insensitive). |

## 3. Check catalog

Ids are `LAYER-NNN`, stable forever (a retired check keeps its id in a
"retired" table in `docs/doctor-checks.md`; ids are never reused). Numbers
step by 10 so a check can be inserted. Columns: Sev = severity (B blocker,
E error, W warning, I info). "Detects by" lists the probes; "Modes" lists the
failure modes the check tells apart, each of which has its own remediation.
`pass` conditions are stated where they are not obvious.

### 3.1 PLAT: OS and platform

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| PLAT-010 | Supported OS and version | B | `platform.system()`, `platform.release()`, `platform.mac_ver()`, `sys.getwindowsversion()`; WSL detection per section 2 | `unsupported-os` (not Windows 10+/macOS 12+/Linux glibc 2.28+), `wsl1` (WSL 1 has no USB path at all: move to WSL 2 or Windows), `eol-os` (W: known end-of-life release) |
| PLAT-020 | CPU architecture matches the installed wheel | B | `platform.machine()` vs the tag recorded in `sadi_py` at build (`sadi_py.BUILD_TARGET`) | `arch-mismatch` (x86_64 Python on arm64 macOS under Rosetta, or the reverse), `unknown-arch` |
| PLAT-030 | Locale and encoding | W | `locale.getpreferredencoding(False)`, `sys.flags.utf8_mode`, `PYTHONIOENCODING` | `non-utf8-console` (Windows code page not 65001 and UTF-8 mode off: the micro sign and the plus-minus sign print as `?`), `c-locale` (Linux `LANG=C` or unset) |
| PLAT-040 | Windows long paths and reserved names | W | Registry `HKLM\SYSTEM\CurrentControlSet\Control\FileSystem\LongPathsEnabled`; data root path length; path components vs `CON PRN AUX NUL COM1-9 LPT1-9` (portability.md section 5) | `long-paths-off` (only when the data root plus the longest session path exceeds 200 chars), `reserved-name-in-path`, `trailing-dot-or-space` |
| PLAT-050 | Environment variables that change SADI behaviour | I | Presence of `SADI_*` (`SADI_FAILPOINTS`, `SADI_FAILPOINT_SEED`, `SADI_DATA_ROOT`, `SADI_API_PORT`, `SADI_LOG_LEVEL`), `PYTHONPATH`, `VIRTUAL_ENV` | `failpoints-armed` (W, `SADI_FAILPOINTS` set outside tests: the store will inject faults on purpose), `pythonpath-set` (I), `other-venv-active` (I) |

### 3.2 PY: Python and uv environment

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| PY-010 | Python interpreter version | B | `sys.version_info` vs `requires-python` of the installed `sadi` distribution (`importlib.metadata`) | `too-old`, `too-new` (W: untested minor), `debug-build` (I) |
| PY-020 | `sadi` package importable and consistent | B | `importlib.metadata.version("sadi")`, `sadi.__file__`, `sadi.__version__`; compare module path with the distribution's `RECORD` | `not-installed`, `version-mismatch` (metadata differs from `__version__`: a stale editable install), `shadowed` (a `sadi/` directory on `sys.path[0]` or the CWD shadows the installed package) |
| PY-030 | Required dependencies present and importable | B | For each entry in the distribution's `Requires-Dist`: `importlib.metadata.version`, then `import` of the top-level module for the hard set (`pydantic`, `typani`, `fastapi`, `uvicorn`, `numpy`, `crc32c`, `sadi_py`) | `missing` (lists names), `import-error` (installed but import raises: records the exception type and message), `pydantic-v1` (B: pydantic 1.x found) |
| PY-040 | uv available (developer and uv-installed layouts only) | W | `shutil.which("uv")`, `uv --version`; a lab wheel install without uv is `skip/not-applicable` when `sadi` was not installed from a `uv` project (`direct_url.json`) | `uv-missing`, `uv-old` (older than the version pinned in `python/pyproject.toml` `[tool.uv] required-version`) |
| PY-050 | Virtual environment is the one SADI was installed into | W | `sys.prefix` vs `direct_url.json`/`python/.venv`; `VIRTUAL_ENV` | `wrong-venv` (a different venv is active than the one `sadi` lives in), `system-python` (I: installed into the system interpreter) |
| PY-060 | Package integrity | W | `RECORD` hashes of `sadi/**` and `sadi/web/dist/**` (sha256) sampled: all files of `sadi.doctor`, `sadi.store`, and `index.html` | `modified-files` (lists paths), `missing-files` |

### 3.3 EXT: Rust extension `sadi_py`

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| EXT-010 | `sadi_py` imports | B | `import sadi_py` in a subprocess with a 20 s timeout (so an ABI crash cannot take the doctor down); captures stderr | `not-installed` (`ModuleNotFoundError`), `abi-mismatch` (`ImportError` naming `PyInit`, `GLIBC_`, `dlopen`, `DLL load failed` or `incompatible architecture`: records which), `crashed` (non-zero exit without a Python traceback), `timeout` |
| EXT-020 | `sadi_py` version matches `sadi` | B | `sadi_py.__version__`, `sadi_py.PROTOCOL_VERSION`, compared with `sadi.__version__` and `sadi.core.PROTOCOL_VERSION` | `version-mismatch` (text names both), `protocol-mismatch` |
| EXT-030 | Windows runtime dependencies | B | Windows only: `sadi_py*.pyd` loads; on failure `dumpbin`-free check for `vcruntime140.dll` and `vcruntime140_1.dll` via `ctypes.util.find_library` | `missing-vcruntime` |
| EXT-040 | Linux udev feature compiled in | W | Linux/WSL only: `sadi_py.serial_features()` reports `udev`; without it `list_ports` cannot report VID/PID (device/serial.md) | `no-udev-feature` (device auto-detection by VID/PID is unavailable; explicit `--port` works) |
| EXT-050 | Extension self-test | E | `sadi_py.selftest()` (codec round trip of `docs/protocol-vectors.json`, decoder resync, simulator one-packet run; pure CPU, under 1 s) | `vectors-fail` (B: the codec disagrees with the committed vectors: a broken build), `timeout` |

### 3.4 WEB: UI bundle

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| WEB-010 | Built UI bundle present | B | `importlib.resources.files("sadi") / "web" / "dist" / "index.html"` exists and is non-empty; the asset manifest it references exists | `missing-bundle` (wheel built without the UI, or a source checkout without `npm run build`), `partial-bundle` (index present, referenced assets missing), `dev-mode` (I: `SADI_WEB_DEV` points at a Vite dev server) |
| WEB-020 | Bundle version matches the server | W | `dist/version.json` `{sadi, git_sha}` vs `sadi.__version__` | `stale-bundle` |

### 3.5 NET: ports and loopback

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| NET-010 | Loopback works | B | `socket` bind to `127.0.0.1:0`, connect, one byte round trip; `getaddrinfo("localhost")` | `no-loopback` (firewall or broken network stack), `localhost-not-loopback` (`localhost` resolves to something other than `127.0.0.1`/`::1`) |
| NET-020 | API port available | E | Bind `127.0.0.1:<port>` (`SADI_API_PORT`, default 8000) with `SO_REUSEADDR` off; on `EADDRINUSE` identify the holder: `psutil.net_connections` when available, else `ss -ltnp`/`Get-NetTCPConnection`/`lsof -nP -iTCP:<port>` | `port-in-use-by-sadi` (W: SADI is already running, says so and offers to open the browser instead), `port-in-use-other` (names the process when it can), `port-privileged` (port below 1024 on POSIX), `bind-denied` (Windows excluded port range: `netsh int ipv4 show excludedportrange protocol=tcp`) |
| NET-030 | WebSocket allowed through local proxy settings | W | `HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY` environment; Windows WinINET proxy via registry `ProxyEnable`; checks `localhost`/`127.0.0.1` are excluded | `proxy-intercepts-localhost` |
| NET-040 | Launcher URL reachable (post-launch mode only) | E | When `--running` is given or NET-020 found SADI: `GET http://127.0.0.1:<port>/api/health` with a 2 s timeout; compares `version` | `health-timeout`, `health-version-mismatch` (another SADI version is running), `health-500` |

### 3.6 DATA: data root

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| DATA-010 | Data root resolved and exists | B | Resolution order `--data-root`, `SADI_DATA_ROOT`, config file, per-OS default (data-safety.md 8.1); `Path.exists()`, `is_dir()`, `os.access(W_OK)`; a probe file is NOT created (read-only) | `missing` (first run: the fix is `sadi doctor fix DATA-010`, which prints the steps and points to the Setup screen; the doctor never creates the data root, decision D2), `not-a-directory`, `not-writable` (owner and mode shown), `unresolvable` (relative path or `~` not expanded in config) |
| DATA-020 | Filesystem type is safe for durability | B/W | Linux: `/proc/mounts` mount containing the root; macOS: `statfs` `f_fstypename`; Windows: `GetVolumeInformationW`, `GetDriveTypeW`, UNC detection (data-safety.md section 10 table) | `network-fs` (B unless `--allow-network-fs`: nfs, cifs, smb, sshfs, rclone, DRIVE_REMOTE), `drvfs-9p` (B on WSL: `/mnt/c`: fsync and flock unreliable), `fat-exfat` (W: no directory durability on Windows, no F_FULLFSYNC on macOS), `removable` (I), `unknown-fs` (W) |
| DATA-030 | Free space | B/W | `shutil.disk_usage(root)` vs `MIN_FREE_BYTES` 2 GiB, `LOW_SPACE_WARN_BYTES` 512 MiB (data-safety.md 6.5); also an estimate in minutes of raw acquisition at 612 kB/s | `below-minimum` (B), `low` (W: under 10 GiB), `quota-suspect` (I: `disk_usage` reports far more free than the user quota: `quota -s` on Linux when present) |
| DATA-040 | Flush primitive works on this volume | B/W | fsync needs a writable fd, so this check is `skip/read-only` unless `--allow-probe-write` is given; then it creates, fsyncs and deletes one file under `<root>/doctor/` (never under `sessions/`) and reports `F_FULLFSYNC` support and latency | `fsync-unsupported` (B), `fullfsync-fallback` (W, macOS), `fsync-slow` (W: over 200 ms p50 over 5 flushes: HDD, USB stick or AV) |
| DATA-050 | Lock primitive works on this volume | B | `fcntl.flock`/`msvcrt.locking` on a read-only fd of an existing file under the root (`sessions/` directory entry itself or `<root>/config.toml`); `ENOLCK` and `EOPNOTSUPP` are the signals (data-safety.md section 10, WSL note) | `locks-unsupported` (B), `lock-held-by-other` (I: the probe target is locked: another SADI is running) |
| DATA-060 | Antivirus or indexer interference (Windows) | W | `Get-MpPreference` `ExclusionPath` contains the root; Windows Search indexer scope via `HKLM\SOFTWARE\Microsoft\Windows Search\CrawlScopeManager` read; macOS Spotlight `mdutil -s <volume>`; the log file for `DurableSharingViolation` events in the last 7 days | `not-excluded-from-defender` (W, I when no sharing violations were ever logged), `indexer-scans-root` (I), `sharing-violations-logged` (W: count and last time) |
| DATA-070 | Config file parses | B | `<root>/config.toml` (or `--config`) parses as TOML and validates as `sadi.core.config.Config` (pydantic); unknown keys listed | `syntax-error` (line and column), `invalid-value` (field path and message), `unknown-keys` (W) |
| DATA-080 | Log directory writable and log size | W | Log path from `logging_setup`; `os.access`; size of the current and rotated logs | `not-writable`, `oversized` (W: over 1 GiB: suggests the retention setting) |
| DATA-090 | Spill files present | W | `<root>/spill/*.wal`, per-user spill dir, OS temp dir spill files (data-safety.md 6.5 step 4) | `spill-present` (lists files, sizes and dates; remediation is "open SADI and import" because the import is a data operation) |

### 3.7 SESS: session directories

Runs over `<root>/sessions/*` read-only via `open_readonly` and
`probe_lock`/`read_lock_holder` (store/session.md). Results are per session
directory; the check status is the worst of them and the evidence carries one
row per directory.

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| SESS-010 | Session directory names and layout | W | Name matches `<YYYYMMDD>T<HHMMSS>Z-<slug>.v<NNN>`; required children `wal/`, `lock`; `manifest.json` parses as `Manifest` | `foreign-dir` (I: a directory not created by SADI; never touched), `incomplete` (I: no valid `seg-000001.wal` header: skipped by the app, safe to ignore), `manifest-unparseable` (W: derived cache, regenerated on next writable open), `manifest-stale` (I) |
| SESS-020 | Locks: live holders and crashed sessions | W | `probe_lock` without acquiring (a non-blocking try followed by immediate release is a mutation of lock state and is NOT done; instead `read_lock_holder` plus the liveness token); state from the manifest and the last record | `locked-live` (I: pid, start time, host: "SADI is open on this session"), `locked-dead-pid-reused` (I: liveness token mismatch), `crashed` (W: state `open`, no `SESSION_CLOSE`, holder dead: "this session was not closed; resume it from the app to continue"), `lock-on-network-fs` (W) |
| SESS-030 | Orphans and leftovers | I | `.tmp` files in `snapshots/` and `exports/`, `manifest.json.tmp-*`, exports without `.prov.json` sidecar, `.staging/` contents | `tmp-leftovers` (I: counts; harmless, never deleted), `export-without-sidecar` (W: listed as `incomplete` by the app) |
| SESS-040 | Family chain consistency | E | For each family: versions contiguous, `parent`/`parent_last_seq` in each manifest match the parent's scan (data-safety.md 5.4) | `version-gap`, `parent-mismatch` (E: tampering or copy error; never auto-fixed), `parent-missing` (W: the parent directory is absent: the family was partially moved) |
| SESS-050 | Permissions and ownership | W | `os.stat` owner and mode on each directory vs current user; Windows ACL read via `os.access` per file | `not-owned-by-user` (W), `read-only-session` (W: cannot be resumed) |

### 3.8 WAL: integrity scan

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| WAL-010 | Quick scan: headers, last segment tail | W | For each session version: `WalReader.scan` limited to segment headers plus the last segment's full frame walk (bounded: under 256 MiB per session) | `torn-tail` (I: normal after a crash: offset, length, sha256; "resume from the app; nothing is lost that was shown as saved"), `corrupt` (E: segment, offset, reason; "do not resume; start a new session and keep this directory for review"), `unsupported-format` (W: newer SADI wrote it), `header-invalid` |
| WAL-020 | Full scan: every record CRC and every seal hash | W | Only with `--deep`: `WalReader.records()` over all segments and SHA-256 of sealed segments (data-safety.md 5.1); progress reported per segment; time bounded by `--deep-timeout` (default 10 min) | same modes as WAL-010 plus `seal-mismatch` (E), `seq-gap` (E), `deep-timeout` (skip with partial evidence) |
| WAL-030 | Snapshot validity | I | `snapshots/snap-*.snap` frames parse, CRC valid, `covers_seq <= last_seq`, `prefix_hash` matches the scan at `covers_seq` (data-safety.md 9.1) | `stale-snapshots` (I: ignored by replay), `invalid-snapshot` (I: CRC or hash mismatch; ignored and never deleted) |
| WAL-040 | Settings record precedes raw data | E | First `RAW_BLOCK` of each version is preceded by a `SETTINGS` record with ADC range codes (data-safety.md 2.2) | `undecodable-version` (E: raw data cannot be scaled; "export raw and contact support") |

### 3.9 USB: device presence, driver, permissions

Everything here is per portability.md and is marked UNVERIFIED until the
hardware session (hardware-verification.md rows 1, 2); the doctor reports
observations and never assumes which channel of a multi-channel part is
SADI's.

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| USB-010 | USB enumeration tool available | W | Linux: `lsusb` on PATH or `/sys/bus/usb/devices` readable; macOS: `system_profiler`; Windows: PowerShell `Get-PnpDevice`; WSL: `lsusb` inside, `usbipd.exe` on the Windows PATH via `/mnt/c/Windows/System32/usbipd.exe` or `usbipd.exe` resolvable | `no-enumeration-tool` (W: skip USB-020 with reason), `usbipd-missing` (E on WSL: install step), `usbipd-old` (W: older than 4.0, different CLI) |
| USB-020 | FTDI device visible to the OS | E | VID 0x0403 with PID in `FTDI_ALLOW_LIST` (0x6010, 0x6014, 0x6001) from the enumeration probe; product string and serial recorded; WSL: `usbipd list` state column (`Not shared`, `Shared`, `Attached`) | `no-device` ("plug in the board and its power supply"), `device-on-windows-side` (WSL: listed by usbipd but not attached), `shared-not-attached` (WSL), `attached-elsewhere` (WSL: attached to another distro), `multiple-devices` (I: more than one SADI candidate; which one is used must be chosen in Setup), `unknown-ftdi-pid` (W: FTDI present, PID not on the allow list) |
| USB-030 | Driver bound: VCP, not D2XX | E | Linux/WSL: `/sys/bus/usb/devices/<id>/<id>:1.0/driver` symlink is `ftdi_sio`; `lsmod`; Windows: `Get-PnpDevice` class `Ports` with a `COM` friendly name vs class `USB` only ("USB Serial Converter" without a child port means VCP unloaded); macOS: `ioreg -p IOUSB -l` and the presence of `/dev/cu.usbserial-*`; `kextstat` for `com.FTDI.driver` (legacy kext, portability.md section 2) | `no-driver` (Linux: `ftdi_sio` not loaded; WSL kernel may lack it), `d2xx-bound` (Linux: `ftdi_sio` unbound or blacklisted; Windows: "Load VCP" unchecked), `legacy-kext` (macOS), `driver-error-code` (Windows: device status code, e.g. 10, 28, 43) |
| USB-040 | Serial node exists and is the expected name shape | E | Linux: `/dev/serial/by-id/usb-FTDI_*` and `/dev/ttyUSB*`; macOS: `/dev/cu.usbserial-*`; Windows: `[System.IO.Ports.SerialPort]::GetPortNames()` and `Win32_SerialPort`; cross-checked with `sadi_py.list_ports()` | `node-missing-driver-ok` (enumerated and driver bound but no node: replug), `com-number-above-9` (I: fine; the crate adds `\\.\`), `by-id-missing` (I: Linux without `/dev/serial`: udev not running, WSL without systemd), `tty-not-cu` (I, macOS: config names `tty.*`: use `cu.*`) |
| USB-050 | Permission to open the node | E | Linux/WSL: `os.access(node, R_OK|W_OK)`, group of the node, `os.getgroups()`, presence of `/etc/udev/rules.d/99-sadi.rules` (hash vs `packaging/udev/99-sadi.rules`), `getent group dialout uucp plugdev`; macOS: `os.access`; Windows: no open is attempted (an open-and-close could disturb a running session), `Win32_SerialPort.Status` and `Get-PnpDevice.Status` are read instead | `not-in-group` (names the group the node uses: `dialout`, `uucp` or `plugdev`), `group-change-pending` (I: user is in the group in `/etc/group` but not in the current session: log out and in), `udev-rules-missing`, `udev-rules-outdated` (hash differs), `udev-not-reloaded` (rules present, node mode not 0660/group), `wsl-no-udev` (WSL without systemd: rules never apply; chmod step) |
| USB-060 | Node not held by another program | E | Linux/macOS: `fuser`/`lsof` on the node; Windows: `Get-Process` names in a known list (`LabVIEW`, `FT_Prog`, `NIMAX`, `putty`, `TeraTerm`) plus `Win32_SerialPort` open status | `held-by-sadi` (I: SADI is running), `held-by-labview` (portability.md: close the VI), `held-by-other` (names pid and process), `modemmanager-probing` (Linux: `ModemManager` active and no `ID_MM_DEVICE_IGNORE` rule) |
| USB-070 | FTDI latency timer and buffer (Linux only, informational) | I | `/sys/bus/usb-serial/devices/ttyUSBn/latency_timer` | `latency-not-2ms` (I: hardware-verification.md row 1 is pending; report only) |
| USB-080 | usbipd attach health (WSL only) | E | `usbipd list` shows `Attached`; inside WSL `dmesg` last 200 lines for `usbip` or `vhci_hcd` errors; kernel config `CONFIG_USB_SERIAL_FTDI_SIO` from `/proc/config.gz` or `/boot/config-$(uname -r)` | `attached-no-node` (kernel lacks `ftdi_sio`: custom kernel or `modprobe`), `vhci-missing` (kernel lacks `vhci_hcd`), `attach-dropped` (dmesg shows disconnect; auto-attach step) |

### 3.10 DEV: device protocol probe

Active probes talk to the board. They are skipped (`skip/port-busy`) when
USB-060 found a holder, so a running acquisition is never disturbed. The
exchange is Query only unless `--with-reset` is given (device/session.md:
Reset reboots the board and must never be sent during a test).

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| DEV-010 | Port opens | E | `sadi_py.open_probe(port)` (serial open, purge, close); records the baud applied | `open-denied` (permission after all: points back at USB-050), `open-busy`, `open-io-error` (errno and text) |
| DEV-020 | Query answered | E | Query with the retry policy of device/session.md (200 ms, 2 s); the Version packet type, firmware version and state byte recorded | `no-reply` (board unpowered, wrong channel on a multi-channel part, or wrong port), `garbage-reply` (bytes arrive, no valid frame after resync: wrong baud or wrong device on this port; first 64 bytes hex in evidence), `unexpected-firmware` (W: not v1.003 and not 3.41) |
| DEV-030 | Firmware state sane | W | State byte: Booted (1), Stopped (2), Streaming (3) | `streaming-unattended` (W: the board is streaming with no SADI process: a previous run died; "start SADI and press Stop, or power-cycle the board"), `unknown-state` |
| DEV-040 | Short stream sanity (opt-in) | W | Only with `--stream-seconds N` (default 0): Start, read N seconds, Stop; packets/s, msgCount gaps, dropped bytes, per-channel saturation (device/session.md `BlockStats`) | `low-rate` (W: under 900 packets/s: USB bandwidth, usbip latency, hub), `gaps` (W), `saturated-channel` (I: LVDT at the rail or disconnected), `stop-not-acked` (E) |
| DEV-050 | Reset and boot time (opt-in) | I | Only with `--with-reset`: Reset, poll Query, time to first reply (hardware-verification.md row 6) | `boot-timeout` (E), `boot-slow` (I: report only until row 6 is verified) |

### 3.11 SIM: simulator self-test

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| SIM-010 | Simulator runs the connect sequence | E | `sadi_py.Session` against `SimDevice` scenario `clean`, virtual clock: connect, start, 100 packets, stop; checks msgCount continuity and that decoded values match the scenario's known values (device/simulator.md tests) | `sim-connect-fail`, `sim-data-mismatch` (B: the codec or scaling is broken in this build), `sim-timeout` |
| SIM-020 | All built-in scenarios load | W | `sim::scenario::SCENARIO_NAMES` each constructed | `scenario-load-fail` (names which) |

### 3.12 CLK: clock and timezone

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| CLK-010 | Wall clock plausible | W | `time.time()` vs build date of `sadi` (must be after) and vs the newest session directory timestamp (must not be before by more than 1 h) | `clock-before-build` (W: session names will sort wrongly; "set the clock"), `clock-before-last-session` (W) |
| CLK-020 | Monotonic clock resolution | I | `time.get_clock_info("monotonic").resolution`; Windows timer resolution | `coarse-monotonic` (I: over 1 ms; affects `mono_ns` in RAW_BLOCK only) |
| CLK-030 | Timezone resolvable | I | `datetime.now().astimezone().tzinfo`, `TZ` env, `/etc/localtime` | `tz-unknown` (I: UI shows UTC) |
| CLK-040 | Time sync status | I | Linux `timedatectl show -p NTPSynchronized`; macOS `systemsetup -getusingnetworktime` (may need admin: skip if denied); Windows `w32tm /query /status` | `not-synced` (I) |

### 3.13 RES: CPU, RAM, process limits

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| RES-010 | CPU count and worker budget | W | `os.cpu_count()`; `WORKER_COUNT = max(1, min(4, cpu-1))` (concurrency.md section 1); `--workers` override | `single-core` (W: workers share the core with acquisition), `workers-exceed-cpus` (W: `--workers` larger than cpu count) |
| RES-020 | Available memory | W | `psutil.virtual_memory().available` when psutil is installed, else `/proc/meminfo`, `sysctl hw.memsize` + `vm_stat`, `GlobalMemoryStatusEx`; need: 512 MiB for the server plus 64 MiB WAL queue plus 256 MiB per worker | `low-memory` (W), `very-low-memory` (E: under the server need) |
| RES-030 | File descriptor and handle limits | W | POSIX `resource.getrlimit(RLIMIT_NOFILE)` soft limit >= 1024; Windows n/a | `low-nofile` (W) |
| RES-040 | Power and thermal state | I | Laptop on battery (`psutil.sensors_battery`, `/sys/class/power_supply`, `pmset -g batt`, `Win32_Battery`); Windows power plan | `on-battery` (I: USB power saving may suspend the FTDI; "plug in the charger"), `usb-selective-suspend` (W, Windows: `powercfg /q` shows USB selective suspend enabled) |

### 3.14 WRK: worker pool spawn test

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| WRK-010 | A worker process spawns and answers | E | `multiprocessing.get_context("spawn")`, run `sadi.jobs.worker.selftest` with a 30 s timeout: the worker imports `sadi` (not `sadi.store`), echoes a pydantic model and exits 0 | `spawn-fail` (text of the child's stderr: usually `sadi` not importable in the child because of a wrong venv or a frozen-entry-point issue), `spawn-slow` (W: over 10 s on Windows: antivirus scanning Python), `child-imports-store` (B: programmer bug, detected by the child's module list) |
| WRK-020 | Worker watchdog exits on parent death | W | Spawn a worker with a pipe, close the parent end, assert exit within 5 s (concurrency.md section 1) | `orphan-survives` (W) |

### 3.15 BRW: browser launch

| Id | Check | Sev | Detects by | Modes |
|---|---|---|---|---|
| BRW-010 | A browser can be launched | W | `webbrowser.get()` resolves a controller; on WSL `wslview` or `explorer.exe` on PATH, `BROWSER` env; Windows default browser from `HKCU\...\UrlAssociations\http\UserChoice` | `no-browser` (W: the URL is printed; "open it by hand"), `wsl-no-wslview` (W: install `wslu` or set `BROWSER=explorer.exe`), `text-browser-only` (W: `lynx`/`w3m`: the UI needs a graphical browser) |
| BRW-020 | Browser is supported | I | Version of the default browser via registry (Windows), `defaults read` (macOS), `--version` of the resolved binary (Linux); minimum: Chromium 110, Firefox 115, Safari 16 | `old-browser` (W), `unknown-browser` (I) |
| BRW-030 | Launch dry run (opt-in) | I | Only with `--open-browser`: open `http://127.0.0.1:<port>/doctor-ping` served by a throwaway listener; wait 10 s for the GET | `launch-no-hit` (W: a browser started but never fetched: proxy or wrong default) |

### 3.16 PLG: plugins

Implemented by `sadi.plugins.doctor.check_plugins` (see [Plugins](plugins.md)). These
findings use string codes rather than numbered ids. Every finding carries numbered fix
steps; the first usually points at `sadi plugins info <id>`.

| Code | Sev | Meaning and main fix |
|---|---|---|
| `plugin.import_failed` | E | Plugin code raised on import; fix it or `sadi plugins disable <id>` |
| `plugin.bad_contribution` | E | A contribution ref is missing or the wrong type; fix the entrypoint in the manifest |
| `plugin.api_incompatible` | E | Manifest `api_version` excludes this SADI plugin API; upgrade the plugin or SADI |
| `plugin.requires_missing` | E | A required plugin is absent; install or enable it |
| `plugin.requires_version` | E | A required plugin has an unsupported version; update it |
| `plugin.duplicate_id` | E | Two plugins use one id; remove or rename one |
| `plugin.bad_candidate` | E | A source entry could not become a plugin; fix the entry in the note |
| `plugin.bad_toml` | E | `sadi_plugin.toml` is not valid TOML; fix the syntax |
| `plugin.bad_manifest` | E | A manifest field is missing or invalid; correct the named field |
| `plugin.manifest_unreadable` | E | Manifest file cannot be read; check path and permissions |
| `plugin.local_dir_unreadable` | E | A local plugin dir has no manifest or cannot be read; fix or remove it from `SADI_PLUGIN_PATH` / `plugins/` |
| `plugin.source_unavailable` | E | A whole source could not be listed; check `SADI_PLUGIN_PATH` and `plugin_paths` |
| `plugin.unhealthy` | E | A record is failed with no more specific cause; see `sadi plugins info` |
| `plugin.unknown_error` | E | Unrecognised error kind; disable the plugin until fixed |
| `plugin.disabled` | W | Plugin is disabled; `sadi plugins enable <id>` |
| `session.plugin_missing` | W | A session used a plugin that is missing or disabled; install or enable it, data stays readable |
| `session.plugin_version_changed` | I | A session used another plugin version; install that version to reproduce exactly |

## 4. Remediation format

### 4.1 Shape

A remediation is produced for one `(check, failure mode, os)` triple and
rendered identically in text, JSON and the UI (section 6 `Remediation`):

```
X USB-050  Permission to open the device node                    [error]
  The board is plugged in but your user may not open /dev/ttyUSB0.
  Fix: add your user to the "dialout" group and install the udev rule.

  1. Add your user to the group that owns the port.
       $ sudo usermod -aG dialout "$USER"
     Expect: no output. (You will be asked for your password.)
  2. Install the SADI udev rule so the port is usable without sudo.
       $ sudo install -m 0644 "$(sadi paths udev-rules)" /etc/udev/rules.d/99-sadi.rules
       $ sudo udevadm control --reload-rules && sudo udevadm trigger
     Expect: no output.
     Changes: system configuration (udev rule file). Never touches SADI data.
  3. Log out and log in again (group changes apply to new logins only),
     then unplug and replug the board.
     Expect: after login, `id -nG` lists dialout.
  4. Verify.
       $ sadi doctor --check USB-050
     Expect: "USB-050 pass".

  Details: node=/dev/ttyUSB0 mode=0660 group=dialout user_groups=[logan,users]
           rules=/etc/udev/rules.d/99-sadi.rules missing
  Docs: docs/portability.md section 4
```

Rules:

1. Title line: status glyph (`.` pass, `!` warn, `X` fail, `-` skip), id,
   check title, severity in brackets.
2. Two sentences: what happened in plain words; what to do, beginning with
   "Fix:" and a verb (ux.md section 6).
3. Numbered steps. Each step has: a one-line instruction starting with a
   verb; zero or more `command` lines for the detected OS, prefixed by the
   shell prompt glyph for that OS (`$` for bash/zsh on Linux, WSL and macOS,
   `PS>` for PowerShell on Windows, `C:\>` for cmd only where PowerShell is
   unavailable); an `Expect:` line with the output the user should see
   (quoted literally where it is literal, described where it varies); an
   optional `Changes:` line stating the mutation class (section 4.3) whenever
   the step changes anything at all; an optional `If not:` line pointing at
   the next failure mode to check.
4. Commands are complete and copy-paste safe: absolute paths or paths the
   doctor resolved (`$(sadi paths udev-rules)` resolves inside the package),
   quoted arguments, no placeholders in angle brackets unless the doctor
   genuinely cannot know the value, in which case the step says where to read
   it (e.g. "the BUSID column of the previous output").
5. Steps that require a different machine or context are labelled: on WSL,
   steps that run in PowerShell on the Windows side are prefixed
   `[Windows PowerShell, as Administrator]`, steps inside the distro
   `[WSL terminal]`.
6. The last step is always `Verify.` and runs `sadi doctor --check <id>`
   (the UI runs the same check with its re-run button); its `Expect:` is the
   pass line. A remediation without a verify step is rejected by the schema
   validator (`Remediation.steps[-1].kind == "verify"`).
7. Steps are ordered least invasive first: replug before reinstall, user
   group before udev rule, close the other program before killing it.
8. Per-OS variants are separate `Remediation` objects, selected by the
   detected OS; `--os <name>` renders another OS's variant (for a helper
   sitting at a different machine) and says so in the title.

### 4.2 Manual steps

A step may have no command (`commands == []`), for physical actions ("Plug
the 12 V supply into the board and check the green LED") or GUI actions
("Open Device Manager: press Win+X, choose Device Manager"). Its `Expect:`
describes what the user should see. GUI steps are used only where no command
exists; where both exist the command comes first and the GUI route follows
as `Or:`.

### 4.3 Mutation classes

Every step carries `mutates`, one of:

| Class | Meaning | Confirmation |
|---|---|---|
| `none` | Reads only (diagnostic commands, `sadi doctor --check`). | none |
| `process` | Starts or stops a program (close LabVIEW, start SADI, kill a process by pid). | the step says which process; the doctor never kills anything itself |
| `system` | OS configuration outside the data root: udev rule, group membership, driver install, usbipd bind, Defender exclusion, registry key, kernel module, clock. | always typed by the user; `sadi doctor fix` performs only the subset in section 4.4 and only after an explicit yes |
| `install` | Installs or reinstalls software (uv sync, wheel reinstall, usbipd, wslu). | typed by the user |
| `data-dir` | Creates or changes files under the data root but never under `sessions/`: creating the root, the config file, the log directory. | NEVER performed by `sadi doctor fix` (decision D2). The step shows the command or says "In SADI, open Setup and choose Change"; the app creates the folder under its own human-confirms rule. |
| `data` | Touches session data (resume, import spill, start a new family). | NEVER a doctor step. The step says "In SADI, open ... and choose Resume"; the app performs it under its own human-confirms rule (ux.md principle 3, data-safety.md 2.3). |

Invariant: no `Remediation` object contains a `data` step with a command. A
test enumerates every remediation and asserts it (section 10.3).

### 4.4 `sadi doctor fix`: the explicit path

`sadi doctor fix <CHECK-ID>` runs the check, picks the remediation for the
detected mode and offers to execute the steps that the doctor knows how to
do safely, one at a time:

```
$ sadi doctor fix USB-050
USB-050 fail: the udev rule is not installed.
Step 1 of 2: Install /etc/udev/rules.d/99-sadi.rules.
  Changes: system (runs sudo; you will be asked for your password)
Run this step? [y/N] y
  installed /etc/udev/rules.d/99-sadi.rules
Step 2 of 2: Verify.
USB-050 pass: udev rule present
```

Decision D2: `fix` is read-only for the user data dir. It never creates,
writes or changes anything under the data root, including the root itself
and `config.toml`; for a `data-dir` step it prints the command and the Setup
screen route and the user acts. `DATA-010 missing` is therefore not
fixable by the doctor.

Allowed fixable steps (the whole list, none of which touch the data root; anything else prints the command and
asks the user to run it):

| Step | Class | What the doctor does after "y" |
|---|---|---|
| Install `99-sadi.rules` (Linux) | `system` | runs `sudo install ...` and `sudo udevadm ...` as separate subprocesses, output shown; sudo prompts the user itself |
| `usbipd attach --wsl --busid <id>` (WSL, the device was already bound) | `system` | runs `usbipd.exe attach` via interop; bind (which needs Administrator) is never run by the doctor |
| Open the browser at the running SADI | `process` | `webbrowser.open` |

`--yes` answers yes to every prompt for scripted lab setup and is refused
when stdin is not a terminal unless `--yes` is given together with
`--non-interactive`; both flags are logged at WARNING. `fix` never has a
`data` step to offer by construction (section 4.3).

## 5. Worked remediations

Three complete examples that implementers copy as the pattern. Other modes
follow the same shape; the full text of every mode lives in the generated
`docs/doctor-checks.md` (~V3H5CGF).

### 5.1 USB-020/device-on-windows-side (WSL)

```
X USB-020  FTDI device visible to the OS                          [error]
  Windows sees the SADI board (busid 2-3, "USB Serial Converter A/B") but it
  is not attached to WSL, so Linux cannot see it.
  Fix: share the device once as Administrator, then attach it to WSL.

  1. [Windows PowerShell, as Administrator] Share (bind) the device once.
       PS> usbipd list
     Expect: a table; the SADI board shows VID:PID 0403:6010 with STATE
             "Not shared". Note its BUSID (for example 2-3).
       PS> usbipd bind --busid 2-3
     Expect: no output. `usbipd list` now shows STATE "Shared".
     Changes: system (usbipd device policy on Windows). Done once per device.
  2. [Windows PowerShell] Attach the device to WSL.
       PS> usbipd attach --wsl --busid 2-3
     Expect: "usbipd: info: Using WSL distribution 'Ubuntu' to attach;
             the device will be available in all WSL 2 distributions."
     Changes: process (Windows loses the COM port while attached).
     Or:  PS> usbipd attach --wsl --busid 2-3 --auto-attach
          keeps re-attaching after replugs; leave that window open.
  3. [WSL terminal] Confirm Linux sees it.
       $ lsusb -d 0403:
     Expect: one line "Bus 001 Device 00N: ID 0403:6010 Future Technology
             Devices International, Ltd FT2232C/D/H Dual UART/FIFO IC".
       $ ls /dev/ttyUSB*
     Expect: "/dev/ttyUSB0 /dev/ttyUSB1" (two channels on an FT2232H).
     If not: the WSL kernel lacks ftdi_sio; run `sadi doctor --check USB-080`.
  4. Verify.
       $ sadi doctor --check USB-020
     Expect: "USB-020 pass  FTDI 0403:6010 serial=FT... on /dev/ttyUSB0".

  Details: usbipd=4.3.0 busid=2-3 state="Not shared" distro=Ubuntu
  Docs: docs/portability.md section 3
```

### 5.2 USB-030/d2xx-bound (Windows)

```
X USB-030  Driver bound: VCP, not D2XX                            [error]
  The board is present ("USB Serial Converter A") but Windows has not
  created a COM port for it: the FTDI "Load VCP" option is off, or the old
  LabVIEW D2XX setup claimed it.
  Fix: turn on Load VCP for the device, then replug.

  1. Find the device instance.
       PS> Get-PnpDevice -PresentOnly | Where-Object InstanceId -like 'USB\VID_0403*' |
           Format-Table Status, Class, FriendlyName, InstanceId
     Expect: rows with Class "USB" and FriendlyName "USB Serial Converter A"
             (and "B"); no row with Class "Ports".
  2. Enable the virtual COM port.
     Open Device Manager (press Win+X, choose Device Manager), expand
     "Universal Serial Bus controllers", double-click "USB Serial Converter A",
     open the "Advanced" tab, tick "Load VCP", click OK.
     Expect: after a few seconds "Ports (COM & LPT)" gains "USB Serial Port
             (COMn)".
     Changes: system (device property). Does not affect SADI data.
  3. Unplug the board's USB cable, wait 5 seconds, plug it back in.
     Expect: Device Manager shows "USB Serial Port (COMn)".
  4. Confirm the port exists.
       PS> [System.IO.Ports.SerialPort]::GetPortNames()
     Expect: a list containing COMn (for example COM5).
     If not: the FTDI driver may be missing; run `sadi doctor --check USB-030`
             again, it will report "driver-error-code" with the next steps.
  5. Verify.
       PS> sadi doctor --check USB-030
     Expect: "USB-030 pass  ftser2k VCP on COM5".

  Details: instance=USB\VID_0403&PID_6010&MI_00\... class=USB ports=[]
  Docs: docs/portability.md section 2
```

### 5.3 DATA-020/fat-exfat (macOS)

```
! DATA-020  Filesystem type is safe for durability               [warning]
  Your data folder /Volumes/LABSTICK/sadi is on an exFAT drive. exFAT cannot
  flush to the disk platter on macOS (no F_FULLFSYNC), so a power loss can
  lose the last seconds of a run.
  Fix: use a folder on the internal disk, or accept the risk knowingly.

  1. See which disk the folder is on.
       $ diskutil info "$(df /Volumes/LABSTICK/sadi | awk 'NR==2{print $1}')" | grep 'File System'
     Expect: "File System Personality:  ExFAT".
  2. Choose a folder on the internal drive (APFS).
       $ mkdir -p ~/sadi-data && diskutil info "$(df ~/sadi-data | awk 'NR==2{print $1}')" | grep 'File System'
     Expect: "File System Personality:  APFS".
     Changes: data-dir (creates an empty folder in your home directory).
  3. Point SADI at it, either for one launch:
       $ sadi --data-root ~/sadi-data
     or permanently, in SADI: Setup step, "Data folder", Change.
     Expect: the Setup screen shows "Data folder ~/sadi-data".
     Changes: data-dir (config.toml under the new root). Existing sessions on
              the stick are left where they are and stay readable from the
              Review screen via "Open folder".
  4. Verify.
       $ sadi doctor --check DATA-020 --data-root ~/sadi-data
     Expect: "DATA-020 pass  apfs on /dev/disk3s5".

  Details: root=/Volumes/LABSTICK/sadi fstype=exfat fullfsync=unsupported
  Docs: docs/data-safety.md section 10
```

## 6. Result schema

Module `sadi/doctor/schema.py` (~V3H5CGF). All models are frozen pydantic
v2 models, `model_config = ConfigDict(frozen=True, extra="forbid")`, so the
JSON output and the UI's generated TypeScript (`web/src/api/schema.ts` via
`npm run gen:api`) are exactly this. Enumerations are `StrEnum` so JSON
carries the words, not numbers.

```python
class Layer(StrEnum):
    """Subsystem a check belongs to; also the run order (section 9.2)."""
    PLAT = "plat"; PY = "py"; EXT = "ext"; WEB = "web"; NET = "net"
    DATA = "data"; SESS = "sess"; WAL = "wal"; USB = "usb"; DEV = "dev"
    SIM = "sim"; CLK = "clk"; RES = "res"; WRK = "wrk"; BRW = "brw"

class Severity(StrEnum):
    """How bad a fail of this check is for the user."""
    BLOCKER = "blocker"; ERROR = "error"; WARNING = "warning"; INFO = "info"

class Status(StrEnum):
    """Outcome of one run of one check."""
    PASS = "pass"; WARN = "warn"; FAIL = "fail"; SKIP = "skip"

class Os(StrEnum):
    """Detected host OS; WSL is distinct because its fixes differ."""
    WINDOWS = "windows"; LINUX = "linux"; MACOS = "macos"; WSL = "wsl"

class Shell(StrEnum):
    """Shell a command line is written for; drives the prompt glyph."""
    SH = "sh"; POWERSHELL = "powershell"; CMD = "cmd"

class Mutates(StrEnum):
    """Mutation class of a step (section 4.3)."""
    NONE = "none"; PROCESS = "process"; SYSTEM = "system"
    INSTALL = "install"; DATA_DIR = "data-dir"; DATA = "data"

class StepKind(StrEnum):
    """Role of a step; the last step of a remediation must be VERIFY."""
    ACTION = "action"; MANUAL = "manual"; VERIFY = "verify"

class SkipReason(StrEnum):
    """Why a check did not run."""
    NOT_APPLICABLE_OS = "not-applicable-os"
    PREREQUISITE_FAILED = "prerequisite-failed"   # evidence names the check
    OPT_IN = "opt-in"                             # needs a flag (--deep, --with-reset)
    READ_ONLY = "read-only"                       # needs --allow-probe-write
    PORT_BUSY = "port-busy"                       # a session is running
    TOOL_MISSING = "tool-missing"                 # e.g. no lsusb
    TIMEOUT = "timeout"
    DISABLED = "disabled"                         # --skip CHECK-ID
    UNVERIFIED = "unverified"                     # channel A/B probe until hardware exists (D3)

CheckId = Annotated[str, StringConstraints(pattern=r"^[A-Z]{2,4}-\d{3}$")]
ModeId = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(-[a-z0-9]+)*$")]

class Command(BaseModel):
    """One copy-paste command line of a step."""
    shell: Shell
    line: str                      # complete, quoted, no angle-bracket placeholders
    context: str | None = None     # e.g. "Windows PowerShell, as Administrator"
    fixable: bool = False          # True only for the section 4.4 allow-list

class Step(BaseModel):
    """One numbered remediation step with expected output."""
    kind: StepKind
    text: str                      # one line, starts with a verb
    commands: list[Command] = []
    expect: str                    # what the user should see
    mutates: Mutates = Mutates.NONE
    changes: str | None = None     # required when mutates != NONE
    if_not: str | None = None      # pointer to the next mode or check
    alt: str | None = None         # "Or:" GUI route or alternative command

    @model_validator(mode="after")
    def _changes_required(self) -> Self:
        """A mutating step must say what it changes; a data step never has a command."""
        if self.mutates is not Mutates.NONE and not self.changes:
            raise ValueError("mutating step needs `changes`")
        if self.mutates is Mutates.DATA and self.commands:
            raise ValueError("data steps are app actions, never commands")
        return self

class Remediation(BaseModel):
    """Ordered steps for one (check, mode, os) triple."""
    check_id: CheckId
    mode: ModeId
    os: Os
    summary: str                   # "Fix: ..." sentence
    steps: list[Step] = Field(min_length=2)
    docs: list[str] = []           # repo-relative doc links

    @model_validator(mode="after")
    def _ends_with_verify(self) -> Self:
        """Every remediation re-runs its check as the last step."""
        if self.steps[-1].kind is not StepKind.VERIFY:
            raise ValueError("last step must be verify")
        return self

class Evidence(BaseModel):
    """What the probes saw; shown under Details and emitted as JSON."""
    facts: dict[str, str | int | float | bool | None | list[str]]
    commands_run: list[CommandRun] = []    # external tools invoked, read-only
    error: ProbeError | None = None        # when a probe itself failed

class CommandRun(BaseModel):
    """A read-only external command the doctor executed, for transparency."""
    argv: list[str]
    exit_code: int | None          # None on timeout
    stdout_tail: str               # last 2 KiB
    stderr_tail: str
    duration_ms: int

class ProbeError(BaseModel):
    """A probe raised or timed out; the check fails with this attached."""
    kind: Literal["exception", "timeout", "tool-missing"]
    detail: str

class CheckSpec(BaseModel):
    """Static description of a check from the registry (catalog row)."""
    id: CheckId
    layer: Layer
    title: str
    severity: Severity
    applies_to: frozenset[Os]
    depends_on: list[CheckId] = []
    opt_in_flag: str | None = None
    modes: dict[ModeId, str]       # mode -> one-line description
    detection: str                 # prose from section 3

class CheckResult(BaseModel):
    """Outcome of one check in one run."""
    id: CheckId
    title: str
    layer: Layer
    severity: Severity
    status: Status
    headline: str                  # one plain-language sentence
    mode: ModeId | None = None     # set when status is warn or fail
    skip_reason: SkipReason | None = None
    evidence: Evidence
    remediation: Remediation | None = None
    duration_ms: int

    @model_validator(mode="after")
    def _consistency(self) -> Self:
        """warn/fail carry a mode and a remediation; skip carries a reason."""
        if self.status in (Status.WARN, Status.FAIL):
            if self.mode is None or self.remediation is None:
                raise ValueError("warn/fail need mode and remediation")
        if self.status is Status.SKIP and self.skip_reason is None:
            raise ValueError("skip needs skip_reason")
        return self

class Host(BaseModel):
    """Where the run happened."""
    os: Os
    os_version: str
    arch: str
    python: str
    sadi_version: str
    sadi_py_version: str | None
    hostname_hash: str             # sha256 prefix, never the raw hostname
    data_root: str | None
    wsl_distro: str | None = None

class RunOptions(BaseModel):
    """Flags that shaped the run; recorded so a report is reproducible."""
    checks: list[CheckId] | None   # None = all
    layers: list[Layer] | None
    deep: bool = False
    with_reset: bool = False
    stream_seconds: int = 0
    allow_probe_write: bool = False
    allow_network_fs: bool = False
    render_os: Os | None = None    # --os override for remediation text
    port: str | None = None

class Summary(BaseModel):
    """Counts and the overall verdict."""
    counts: dict[Status, int]
    worst_severity_failed: Severity | None
    verdict: Literal["ready", "degraded", "blocked"]
    first_action: str | None       # the single most important fix, for the UI banner

class DoctorReport(BaseModel):
    """Whole run: the JSON document and the UI screen's state."""
    schema_version: Literal[1] = 1
    run_id: UUID
    started_at: AwareDatetime
    finished_at: AwareDatetime
    host: Host
    options: RunOptions
    results: list[CheckResult]     # in run order
    summary: Summary
    log_path: str | None
```

Verdict rule: `blocked` if any `fail` has severity `blocker`; `degraded` if
any `fail` or `warn` remains; otherwise `ready`. `first_action` is the
headline of the first `fail` in layer order (blockers first), else the first
`warn`.

Probe functions return typani `Result[Evidence, ProbeError]`; a `Check`
returns `Result[CheckResult, ProbeError]` and the runner converts an `Err`
into a `fail` with `evidence.error` set and a generic remediation
`<id>/probe-error` ("Re-run with -v and attach the log; this is a doctor
bug, not necessarily a problem with your setup"). Exceptions escaping a
check are programmer bugs and are caught once by the runner, logged at
ERROR with traceback, and reported the same way.

## 7. CLI

```
sadi doctor [OPTIONS]                    run all applicable checks, text report
sadi doctor --json                       same, JSON DoctorReport on stdout
sadi doctor --check USB-050 [--check ...]
sadi doctor --layer usb --layer dev
sadi doctor --skip WAL-020
sadi doctor --deep                       WAL-020 full scan (bounded by --deep-timeout)
sadi doctor --with-reset                 DEV-050 (reboots the board; refused if port busy)
sadi doctor --stream-seconds 5           DEV-040
sadi doctor --allow-probe-write          DATA-040 (creates and deletes one probe file under <root>/doctor/)
sadi doctor --allow-network-fs           downgrade DATA-020 network-fs from blocker to warning
sadi doctor --data-root PATH  --port NAME  --api-port N
sadi doctor --os wsl                     render remediations for another OS
sadi doctor --bundle PATH                also write a support bundle (report JSON + log tail + doctor-checks version) to PATH
sadi doctor --running                    include NET-040 against a running SADI
sadi doctor fix CHECK-ID [--yes] [--non-interactive]
sadi doctor list                         print the catalog (id, layer, severity, title, applies-to)
sadi doctor explain CHECK-ID [--os X]    print every mode and its remediation without running
```

Text rendering: one line per check in run order (`glyph id  title  headline`),
then a blank line and the full block (section 4.1) for every `warn` and
`fail`, ordered blockers first; then the summary line
`Verdict: blocked (2 fail, 3 warn, 41 pass, 4 skip)  Log: <path>`. `-v`
appends the `Details:` block to passes too; `-q` prints the summary line
only. Width 80, ASCII only, no colour unless stdout is a terminal and
`NO_COLOR` is unset; colour is never the only carrier of meaning (ux.md
section 9). When stdout is not a terminal the default output is JSON
(`--text` forces text), mirroring the frob envelope convention the team
already knows.

Exit codes: 0 verdict `ready` or `degraded` with only warnings (decision D4: a run with warnings only exits 0); 1 any `fail`
of severity `error`/`warning`/`info`; 2 any `fail` of severity `blocker`;
64 usage error; 70 the doctor itself crashed (traceback in the log, never on
stdout in JSON mode). `fix` exits 0 when the verify step passes, 1 otherwise,
3 when the user declined.

Mapping between the three surfaces:

| Concept | Text | JSON | UI |
|---|---|---|---|
| check row | `X USB-050  title  headline` | `results[i]` | row in the Doctor table, status glyph and word |
| severity | `[error]` | `severity` | badge text after the title |
| mode | not shown (in Details) | `mode` | shown in the expandable "Details" |
| remediation | numbered block | `remediation.steps[]` | expandable numbered list with a Copy button per command |
| expect | `Expect:` line | `steps[].expect` | grey line under the command |
| mutation class | `Changes:` line | `steps[].mutates`, `changes` | yellow "Changes: ..." note; `fix` button only for `fixable` commands, opens a confirm dialog |
| verify | last step, `sadi doctor --check` | `steps[-1].kind == "verify"` | "Re-run this check" button |
| evidence | `Details:` block | `evidence.facts` | collapsed "Details" |
| verdict | summary line | `summary.verdict`, `first_action` | banner at top: "Ready", "Some things need attention: <first_action>", "SADI cannot run yet: <first_action>" |
| log | `Log:` path | `log_path` | "Open log folder" link |

## 8. UI Doctor screen (~JCJ0197)

Server side: `GET /api/doctor` returns the last `DoctorReport` (or 404
`no-run-yet`), `POST /api/doctor/run` with a `RunOptions` body starts a run
as a job (concurrency.md section 6; key class `interactive`, task
`doctor.run`, runs in a thread of the server process because it must see the
same environment, never in a worker) and streams `CheckResult` events on the
results stream as each check finishes; `POST /api/doctor/run` with
`{"checks": ["USB-050"]}` is the per-check re-run. `POST /api/doctor/fix`
does not exist in v1: fixes stay in the CLI, and the UI shows the exact
command with a Copy button (decision D2).

Wireframe (work area; header, rail and status bar as in ux.md section 2):

```
+-----------------------------------------------+--------------------------+
| DOCTOR                              [Run all] | NEXT ACTION              |
| SADI cannot run yet: your user may not open   | Fix the device           |
| the device (USB-050).                         | permission, then re-run. |
|                                               | [ Re-run USB-050 ]       |
| Layer    Check                      Status    |                          |
| USB      USB-020 Device visible     . pass    | Showing fixes for:       |
| USB      USB-050 Permission to open X fail  v | (o) Linux  ( ) Windows   |
|   The board is plugged in but your user may   | ( ) macOS  ( ) WSL       |
|   not open /dev/ttyUSB0.                      |                          |
|   Fix: add your user to "dialout" and install |                          |
|   the udev rule.                              |                          |
|   1. Add your user to the group.              |                          |
|      $ sudo usermod -aG dialout "$USER"  [Copy]|                          |
|      Expect: no output.                       |                          |
|   2. Install the udev rule.          Changes: |                          |
|      system configuration                     |                          |
|      $ sudo install -m 0644 ...          [Copy]|                          |
|   3. Log out and in, replug the board.        |                          |
|   4. Verify.                  [Re-run check]  |                          |
|   > Details                                   |                          |
| DEV      DEV-010 Port opens         - skip    |                          |
|   Skipped: prerequisite USB-050 failed.       |                          |
| ...                                           |                          |
+-----------------------------------------------+--------------------------+
```

Rules: status by glyph and word, never colour alone; the first failing check
is expanded by default; "Copy" copies one command line; the OS selector
re-renders remediations via `--os` semantics without re-running; the screen
is reachable from the header Help menu on every step, from the Setup step's
device status line ("Not found. [Run Doctor]"), and from every device or
store error dialog's `[Details]` ("Run Doctor" link), per ~JCJ0197
acceptance 2. While a run is in progress rows fill in as events arrive
(nothing blocks the loop; the run is a job).

## 9. Runner

### 9.1 Module map (~V3H5CGF)

```
python/sadi/doctor/
    __init__.py       run(options) -> Result[DoctorReport, DoctorError]; exit_code; summarize
    schema.py         section 6 models
    registry.py       CheckSpec registry; @check and @remedy decorators; ordering
    probes.py         Probes protocol and RealProbes (fs, env, subprocess, usb, net, clock, mem)
    steps.py          step builders (action, cmd, Mutates) and schema invariants
    render_text.py    section 7 text
    checks/           one module per layer; each holds the checks AND their remedies
    cli.py            sadi-doctor: run | list | explain | docs
    __main__.py       python -m sadi.doctor
python/tests/doctor/  FakeProbes double, per-(check, mode) fault injection, invariants
docs/doctor-checks.md generated by `sadi-doctor docs` (test fails when stale)
```

Implementation status and deviations from this spec (~V3H5CGF):

- Entry point is the `sadi-doctor` script and `python -m sadi.doctor`; there is
  no unified `sadi` launcher yet, so `sadi doctor` is not registered.
- Remedies are colocated with their checks in `checks/<layer>.py` (via
  `@remedy(id, mode)`) rather than a separate `remediations/` package.
- The runner is sequential (no thread pool) and has no per-check or whole-run
  timeout budget; probe timeouts live in the subprocess probes only.
- Implemented (34): SESS-010..050, WAL-010..040, PLAT-010/030/050, PY-010/020/030/040, EXT-010, WEB-010,
  NET-010/020, DATA-010/020/030/090, USB-020/030/040/050, CLK-010,
  RES-010/020/030, BRW-010, PLG-010. USB-020 skips as unverified on Windows
  and macOS. The Channel A/B probe is reported as unverified (decision D3).
- Deferred: DEV, SIM and WRK layers; EXT-020..050; NET-030/040;
  PY-050/060; DATA-040..080; USB-010, USB-060..080; CLK-020..040; RES-040;
  BRW-020/030; PLAT-020/040; WEB-020; the `fix` subcommand; `--bundle`.
  Each is tracked as a ticket.
- SESS and WAL use `sadi.doctor.sessions.survey_sessions`, one read-only pass
  per run (cached on the probes) over the store's `read_lock_holder`,
  `read_manifest`, `WalReader.scan`/`records` and snapshot listing; nothing is
  locked, repaired, moved or deleted. Deviations: "crashed" is approximated by
  manifest state open/crashed plus a dead lock holder; sessions over 256 MiB are
  skipped by WAL-010 and covered only by `--deep` (WAL-020); the deep budget is a
  fixed 120 s (`deep-timeout`), not a `--deep-timeout` option; a missing
  manifest is reported as SESS-010 `manifest-stale` (it is a derived cache).
- With `--check`, unselected `depends_on` checks are ignored rather than run.

### 9.2 Order, dependencies, skipping

Checks run in layer order PLAT, PY, EXT, WEB, NET, DATA, SESS, WAL, USB, DEV,
SIM, CLK, RES, WRK, BRW, and within a layer by id. `depends_on` lists hard
prerequisites; when one of them is `fail` the dependent reports
`skip/prerequisite-failed` with the prerequisite id in evidence (never a
cascade of red). Declared dependencies: EXT-* on PY-020; EXT-020..050 on
EXT-010; SESS-* and WAL-* on DATA-010; WAL-* on SESS-010; USB-030..080 on
USB-020; DEV-* on USB-040 and USB-050 and USB-060 (busy -> `skip/port-busy`);
SIM-* on EXT-010; WRK-* on PY-020. Layers without dependencies between them
(NET, CLK, RES, BRW) run concurrently in a small thread pool (4) to keep a
full run under 15 s without `--deep`; results are still reported in catalog
order.

### 9.3 Timeouts

Every probe has a timeout (default 5 s; subprocess imports 20 s; WRK-010
30 s; WAL-020 `--deep-timeout`). A timeout is `ProbeError(kind="timeout")`
and the check fails with mode `timeout` where the catalog lists it, else
`probe-error`. The whole run has a budget (`--timeout`, default 120 s, 15 min
with `--deep`); on expiry remaining checks are `skip/timeout`.

### 9.4 Logging

`_log = get_logger(__name__)`. INFO: run start with options and host, each
check's id, status, mode and duration; WARNING: every `warn`/`fail` with its
evidence facts; ERROR: probe exceptions with traceback; DEBUG: every
subprocess argv, exit code and output tails, every file opened. The log path
is in the report so "Details" can point at it.

### 9.5 Read-only enforcement

1. Probes open files with `os.open(path, O_RDONLY)` (plus `O_BINARY` on
   Windows) and directories via `os.scandir`; no probe imports `os.remove`,
   `os.rename`, `os.replace`, `shutil.rmtree` or `open(..., "w")`: a lint
   test greps `sadi/doctor/checks/**` and `probes.py` for those names and
   fails on any hit outside `fix.py`.
2. Subprocesses run with a fixed argv allow-list per probe (no shell), with
   `cwd` set to a temp dir and `stdin` closed.
3. The store is used only through `open_readonly`, `WalReader.scan`,
   `WalReader.records`, `read_lock_holder` and `probe_lock`'s read path
   (store/session.md: these take no lock and write nothing).
4. Test: every fixture run and the real-world smoke run hash the data-root
   tree (names, sizes, mtimes, bytes) before and after, as the store's
   `readonly-is-readonly` test already does (data-safety.md 12.2), and
   assert equality; `--allow-probe-write` is asserted to touch only
   `<root>/doctor/` and to leave it empty afterwards.

## 10. Test strategy

Everything is fixture-driven: a check never talks to the OS directly, only
through a `Probes` object, so a test substitutes a fake world and asserts
status, mode and the exact remediation text.

### 10.1 World fixtures

`python/tests/doctor/fixtures/<CHECK-ID>/<mode>.<os>.json` is a `FakeWorld`
(pydantic): `os`, `env`, `files` (path -> bytes or a directory marker with
mode and owner), `mounts`, `usb_devices`, `serial_ports`, `processes`,
`sockets_in_use`, `commands` (argv tuple -> `{exit, stdout, stderr}`),
`clock`, `memory`, `cpu_count`, `registry` (Windows keys -> values),
`import_results` (module -> ok or exception text). `FakeProbes(world)`
implements the `Probes` protocol over it and records every call for the
read-only assertions. Each fixture file is named after the mode it must
produce, so the catalog test matrix is the directory listing: a test
enumerates `registry.all_checks()` and asserts that every `(check, mode)`
pair has at least one fixture for every OS in `applies_to`, and that running
the check on that fixture yields exactly that mode. A mode without a fixture
fails CI; a fixture that produces a different mode fails CI.

### 10.2 Golden remediation text

For each fixture the rendered text block is compared with
`fixtures/<CHECK-ID>/<mode>.<os>.txt` (golden, updated with
`pytest --update-goldens` and reviewed in the diff). This pins every command
line, every `Expect:` and every `Changes:` line, which is the ~V3H5CGF
acceptance "assert the remediation text".

### 10.3 Schema and invariants

- `DoctorReport.model_json_schema()` snapshot at
  `python/tests/doctor/schema.snapshot.json`; a test fails on any diff so a
  schema change is a deliberate commit (and the UI regenerates
  `schema.ts`).
- Every fixture run's JSON round-trips: `DoctorReport.model_validate_json(
  report.model_dump_json())` equals the original (frozen models make this
  exact).
- Invariant tests over the whole remediation table (no world needed): last
  step is verify; no `data` step has a command; every mutating step has
  `changes`; every command line is ASCII, has no `<placeholder>` unless the
  step text contains "from the previous output"; every PowerShell command
  uses `PS>` shell and every sh command uses `$`; every `docs:` link
  resolves to an existing file; every check has a remediation for every mode
  for every OS in `applies_to`.

### 10.4 Generated catalog doc

`python -m sadi.doctor.registry --docs > docs/doctor-checks.md` and a test
that regenerates it into a temp file and diffs with the checked-in copy
(same pattern as `gob-dev gen all --check`). That file is the exhaustive
per-mode reference; this file stays the design.

### 10.5 Real-world fault injection

- Store fixtures: a torn tail is produced with the real `WalWriter` and
  `SADI_FAILPOINTS=wal.write.partial=kill` in a subprocess (data-safety.md
  section 11), a corrupt WAL by flipping bits in a sealed copy, an orphaned
  lock by a crashee that is killed; all under `tmp_path` and then handed to
  the real `Probes`. These exercise WAL-010/020 and SESS-020 end to end.
- Simulator: SIM-010 against the real `SimDevice`; DEV-010..030 against a
  `SimDevice` exposed through a pty on POSIX (the `serial_loopback.rs`
  pattern) so the serial path is real; garbage-reply is produced by a pty
  writer sending junk.
- Environment: PY-020/shadowed by prepending a fake `sadi/` dir to
  `sys.path` in a subprocess; EXT-010/abi-mismatch by a stub `sadi_py.so`
  that fails to load; NET-020 by binding the port in the test; DATA-030 by
  monkeypatching `shutil.disk_usage`; DATA-050 on CI by a Linux tmpfs vs an
  `ENOLCK`-raising fake.
- OS matrix: CI runs the fixture suite on all three OSes, and the smoke test
  `sadi doctor --json` on each runner asserts: valid schema, tree hash
  unchanged, no `fail` with severity `blocker` except USB/DEV layers (no
  board on CI: USB-020 `fail/no-device` is the expected outcome there and is
  asserted as such), and total duration under 60 s.
- Hardware rows: `pytest -m hardware` (deselected by default) runs the DEV
  layer against a board and files its evidence under
  `docs/hardware/captures/` per hardware-verification.md section 4.

## 11. Ticket split and follow-ups

| Ticket | Scope | Delivers from this design |
|---|---|---|
| ~V3H5CGF (CLI) | `python/sadi/doctor/**`, `python/tests/doctor/**`, `docs/doctor-checks.md` | sections 3, 4, 6, 7, 9, 10; `sadi doctor`, `fix`, `list`, `explain`; the generated catalog doc; every fixture and golden. Needs a lease widen onto the launcher's CLI entry (`docs/launcher.md` ticket ~0VYJVFZ owns `sadi` argv) to register the subcommand, and onto `python/pyproject.toml` for `psutil` (decision D1). |
| ~JCJ0197 (UI) | `web/src/screens/doctor/**`, API endpoints `GET /api/doctor`, `POST /api/doctor/run` (lease widen onto the server ticket ~X3H80G2's router registration) | section 8; the OS selector; entry points from Setup and error dialogs. Consumes the generated `schema.ts`. |

Follow-ups for the coordinator to file (not in either ticket): (a) `sadi
doctor --bundle` support-bundle format and a privacy review of its contents
(hostnames hashed, serial numbers truncated, no `.env`); (b) a Windows
`fsync_dir` probe once data-safety.md section 16 item 1 lands; (c) a
"doctor ran at startup" banner: the launcher runs the PLAT, PY, EXT, WEB,
NET and DATA layers (under 2 s) before serving and refuses to start on a
`blocker`, printing the first remediation.

## 12. Decisions

Resolved by the user; these supersede any earlier recommendation.

D1. psutil is adopted as the system-metrics dependency (process names
behind ports and device nodes, memory, battery) and is declared in
`python/pyproject.toml`. The shell probes in the catalog remain only as
fallback when the import fails so the doctor still runs.

D2. `sadi doctor fix` stays read-only for the user data dir (section 4.4).
Creating the data root or `config.toml` is done through the app's Setup
"Change" flow, never by the doctor. The UI does not call `fix` at all
(section 8).

D3. The FTDI channel A/B probe is reported as `unverified` until hardware
exists: USB-040 lists both `/dev/ttyUSB0` and `/dev/ttyUSB1` but never
asserts which is SADI's (hardware-verification.md row 1). DEV-020 tries the
configured port only and the `no-reply` remediation says to try the other
channel.

D4. Runs with warnings only exit 0, so a lab script can gate on blockers
(section 7).
