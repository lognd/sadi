# Hardware-verification checklist

Status: current

Single mapping from "needs the physical board" (docs/protocol.md section 10)
to the code or config that encodes each unverified assumption. Work through
the rows on the bench with the `hwprobe` tool (ticket ~X42K86Y,
docs/device/hwprobe.md), commit the raw captures, then apply the follow-up
change in the last column.

Conventions:

- Status column values: `pending`, `pass`, `fail`, `blocked`. Update it in the
  same commit that adds the capture; link the session directory.
- Symbols in the "Encodes assumption" column are the planned `sadi-proto`
  names from docs/plan.md (R1-R3, R5). If a name changes when the crate
  lands, fix it here in the same change.
- hwprobe subcommands: `enumerate`, `query`, `reset-boot-time`,
  `stream-60s-with-gap-stats`, `range-sweep`, `encoder-spin`, `digital-in`.
  Each writes `report.json` plus a raw `.bin` capture.

## 1. Safety notes (read before powering anything)

- LVDT supply: +12 to 20 VDC on RED, -12 to 20 VDC on BLUE; keep the supply
  constant and never hot-swap it with the board streaming (docs/domain.md).
- Input limit: the LVDT output is about +-5 V. Do NOT exceed 5 V on AIN0 in
  normal use; the default range is +-5.12 V (code 1). Before sweeping to
  narrower ranges (codes 2, 3, 11, 7, 15) disconnect the LVDT and drive the
  inputs from a bench source set well inside the selected range; confirm the
  source with a meter first.
- Never apply a negative voltage to a unipolar-range channel, and never apply
  more than the bipolar full scale selected for the current code.
- Use a bench source or shorted inputs (0 V) for all scaling checks; do not
  use the test frame or the load cell/LVDT rig for extremes.
- Encoder-spin: turn the encoder by hand only; no motor drive.
- Reset and watchdog tests (rows 6, 11) will silence the board; do not run them
  while a specimen test is in progress.
- Do not commit anything containing site credentials or serial numbers beyond
  the board label.

## 2. Checklist

| # | Item (protocol.md s10) | Bench procedure | Expected result | Evidence (hwprobe) | Encodes assumption | If pass / if fail | Status |
|---|---|---|---|---|---|---|---|
| 1 | FTDI part and FIFO mode; 612 kB/s at 2 ms latency | Plug in; run `hwprobe enumerate` then `hwprobe stream-60s-with-gap-stats` at latency 2 ms | Device reports FT2232H channel in 245 FIFO mode as "SADI 2.0 A"; sustained about 612 kB/s for 60 s, zero "Saturation detected" purges, no gaps | `enumerate` JSON (VID/PID, description, chip type) and `stream` report (bytes/s, gap histogram, purge count) plus `.bin` | `Transport` impl in R5 (serialport backend): latency timer setting, read buffer size, baud/line config | Pass: freeze the 2 ms default. Fail: raise latency or buffer size in the backend config, record the achieved rate, update protocol.md s1 | pending |
| 2 | ADC part: ADS8684 vs ADS8688; auto-scan channel count | `hwprobe range-sweep` with distinct DC levels on AIN0..AIN3 (and AIN4..AIN7 if exposed) | Channel data is stable per channel; 8 channels cycle if ADS8688, 4 if ADS8684; a wrong assumption shows as data alternating between two sets | Per-channel mean/std table from `range-sweep` report; `.bin` | Decoder channel-count constant (`CHANNELS` / packet layout in R2 `sadi-proto` codec) | Pass: keep four. Fail: change channel count, update vectors in protocol-vectors.json and protocol.md s3 | pending |
| 3 | Unipolar scaling (codes 5/6/7/15) and bipolar extremes | `hwprobe range-sweep` over every supported code with 0 V, +0.5 FS, +FS-, and for bipolar -FS+, -0.5 FS, with a bench source (see safety) | Compare against both `volts_dll` and `volts_ideal`; bipolar raw 0x0000 at <= -FS should decode to -FS; unipolar upper half should be positive and scale `raw/65535*FS` | `range-sweep` report: raw words, both decodings, residual vs meter reading, per code | Codec scaling mode switch (bug-compatible `Dll` vs `Ideal`, R2) and its default | Pass for ideal: make `Ideal` the codec default, keep `Dll` for legacy parity. Pass for DLL formula: default to `Dll` and note in protocol.md s4. Update vectors | pending |
| 4 | Encoder sign convention; high-word continuity | `hwprobe encoder-spin`: turn the encoder a known direction by roughly 3 full 16-bit counter wraps | Positive direction gives increasing count for A=PE2/B=PE3 (or reversed); count continuous across TCC0.CNT wraps with PER=0xFFFF, no jumps | `encoder-spin` report: signed delta series, wrap events, direction; `.bin` | Encoder decode in R2 (position = high word << 16 or TCC0.CNT) and sign flag (config `encoder_invert`) | Pass: keep. Sign reversed: set `encoder_invert` default. Discontinuity: change high-word combine logic and re-derive from protocol.md s3 | pending |
| 5 | Unexpected firmware output; Query/Stop interleaving mid-packet | `hwprobe query` with bad command tails; send Query and Stop while streaming; record all bytes | Firmware emits nothing unexpected; document exact byte interleaving of a response arriving inside a data packet | `query` report: unexpected-byte log, per-case raw `.bin` | Resync `Decoder` and unknown-byte policy (R2); Session read loop (R3) | Pass: strict decoder is fine. Fail: extend Decoder to classify/skip the observed output; add vectors from the capture | pending |
| 6 | Boot time after Reset | `hwprobe reset-boot-time`: send Reset, poll Query until first valid reply, repeat at least 20 times; also with PB4 high and low if accessible | Stable, bounded time to first reply; record min/median/max | `reset-boot-time` report: histogram, timeouts | Session retry/timeout constants (`RESET_TIMEOUT`, `QUERY_RETRY`, R3) | Set timeouts to max observed plus margin (at least 2x); update protocol.md s5 | pending |
| 7 | Digital-input pin mapping and polarity | `hwprobe digital-in`: drive each connector pin high/low individually (3.3 V logic as per board doc) | One PORTD bit changes per pin; map bit n -> pin; active-high or low identified | `digital-in` report: byte value per pin state; `.bin` | Digital-input decode table / polarity flag in R2 codec | Record the mapping in protocol.md s3; set the polarity default and correct the bit order if different | pending |
| 8 | Back-to-back commands | Send duplicates of each command at the DLL cadence (every `a` ms) and in rapid bursts, including repeated Start | Firmware accepts duplicates idempotently; repeated Start re-runs the ADS8688 reset sequence (note any data gap) | `query` and `stream` reports with burst mode; `.bin` | Session command resend policy (R3: retry interval, no duplicate Start) | Pass: allow retry. Fail: forbid resend after Start; resend only Query until state changes | pending |
| 9 | (secondary, optional) v3.41 CRC init 0xFFFF; `55 94 2F 78` -> `55 F6 71 3D 5A 40 D5 D3` | Only if a 3.41 board is available: send the command and capture the reply | Exact reply bytes match | Raw `.bin` of the exchange | v3.41 codec CRC-16/CCITT-FALSE init constant (R6) | Pass: mark vectors verified. Fail: find the real init and update the codec and vectors | pending |
| 10 | (secondary, optional) 16-byte MOM-mode data packet; 0x90/0x63 field consumption | 3.41 board only: request MOM-mode data and log packet lengths | Either a 16-byte packet exists or only the 30-byte form | Raw `.bin`, length histogram | v3.41 packet decoder (R6) | Pass: add the 16-byte form. Fail: drop it and document in protocol.md s8 | pending |
| 11 | (secondary, optional) Stop's watchdog self-reset; silence duration | 3.41 board only: send Stop and time until the next valid reply | Document whether the reset is intentional and the silent interval | `reset-boot-time` style report after Stop | v3.41 session Stop handling and timeout (R6/R3) | Set post-Stop quiet time to observed max plus margin | pending |
| 12 | udev rules grant non-root access (UNVERIFIED, to be confirmed on hardware) | Install `packaging/udev/99-sadi.rules`, reload and trigger, re-plug, then check `ls -l /dev/ttyUSB*` and the raw usb node as a non-root user in `dialout` | Node is group `dialout`, mode 0660; the user opens it without sudo | Command output pasted into session.md | `packaging/udev/99-sadi.rules` (VID/PID matches, GROUP, MODE, TAG) | Pass: drop the UNVERIFIED label. Fail: fix the match keys (for example ATTRS vs ENV on the tty node) and record the distro | pending |
| 13 | `/dev/serial/by-id` naming (UNVERIFIED, to be confirmed on hardware) | List `/dev/serial/by-id/` with the board attached | A stable `usb-FTDI_*-ifNN-port0` link per channel; record the exact names | `ls -l` output in session.md | Port-selection docs in portability.md section 1 | Pass: document the real pattern. Fail: correct the pattern in portability.md | pending |
| 14 | FTDI channel A vs B selection (UNVERIFIED, to be confirmed on hardware) | Enumerate with `hwprobe enumerate`; open each channel in turn | Only one channel (expected A, "SADI 2.0 A") carries the protocol stream; record which interface number and by-id suffix it is | `enumerate` JSON plus by-id listing | Channel choice in the serialport backend (R5) and portability.md section 1 | Pass: pin the channel. Fail: change the default and document | pending |
| 15 | `ftdi_sio` available under WSL2 usbipd (UNVERIFIED, to be confirmed on hardware) | Attach per portability.md section 3; run `lsmod \| grep ftdi_sio`, then `modprobe ftdi_sio` if absent; check that a ttyUSB node appears | Node appears after attach; note whether the stock kernel needed a module or custom kernel; compare stream rate and latency with native | `lsmod`, `dmesg` tail, `uname -r`, hwprobe stream report | portability.md section 3 (currently unverified claim) | Pass: record the kernel version that works. Fail: document the custom-kernel steps | pending |
| 16 | 0403:6001 (FT232R) rule (UNVERIFIED, to be confirmed on hardware) | Only if an FT232R part is ever used: attach and repeat row 12 | Node access matches rows for 6010/6014 | As row 12 | The 0403:6001 lines in `packaging/udev/99-sadi.rules` | Pass: drop the label. Fail/unused: remove the lines | pending |

## 3. Order of work

1. Rows 1, 2 (identify the hardware), then 6, 8 (communication basics).
2. Rows 3, 7, 4 (data semantics).
3. Row 5 last of v1.003 (needs the fault cases).
4. Rows 9-11 only with a 3.41 board.

## 4. Session record template

Copy to `docs/hardware/captures/<YYYY-MM-DD>-<board-label>/session.md`, fill in,
and commit it with the raw `report.json` and `.bin` files.

```
# Session <YYYY-MM-DD> <board-label>

Operator:
Board label / firmware (v1.003 or 3.41):
Host OS / driver version / FTDI latency setting:
hwprobe commit and command line(s):
Bench setup (sources, meters, LVDT connected? supply voltage):
Safety checklist confirmed (section 1): yes/no

| row | subcommand | capture file | result (pass/fail/blocked) | notes |
|---|---|---|---|---|

Deviations from expected results:
Follow-up tickets filed:
```

After the session update the Status column in section 2 and open a ticket for
each "if fail" change.

Until hardware is available, host code is exercised against the protocol-faithful
simulator described in [device/simulator.md](device/simulator.md).

Per-OS port naming, FTDI driver conflicts, udev rules and WSL passthrough are
audited in [portability.md](portability.md); its udev rules are unverified until
this session.
