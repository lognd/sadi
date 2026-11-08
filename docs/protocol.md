# SADI MOM wire protocol (reverse-engineered)
Status: current

Target: Out of the Box Electronics "SADI" data-acquisition board as used in
teaching labs, firmware `SADI_MOM_v1.003.hex` (ATxmega64A3U) with host library
`momLab.dll` v1.003. A secondary section covers the generic firmware
`SADI-3.41HS.hex` with `SADI_FW3.dll`.

Everything below comes from static analysis only (no board was connected):

- `momLab.dll` disassembled with GNU objdump (the DLL still carries its COFF
  symbol table, so static function names are real, not invented). Image base
  0x6d880000; all DLL addresses below are virtual addresses.
- `SADI_MOM_v1.003.hex` (4678 bytes) and `SADI-3.41HS.hex` (11920 bytes)
  disassembled with `avr-objdump -m avr:106`. Firmware addresses are byte
  offsets into flash.
- Vendor "LIB 3.0 reference" text was used only for naming.

Confidence tags used throughout:

- **[FW]** derived from the firmware disassembly (highest authority).
- **[DLL]** derived from the host DLL disassembly.
- **[FW+DLL]** both sides agree.
- **[inferred]** follows from the code but not literally present.
- **[unverified]** plausible but needs the physical board.

Machine-readable test vectors generated from the same analysis live in
`docs/protocol-vectors.json`.

---

## 1. Transport

| Item | Value | Source |
|---|---|---|
| USB bridge | FTDI D2XX device whose description string is exactly `"SADI 2.0 A"` or `"SADI 2.0"` (`findSADIs` @0x6d882080 does `strncmp` with 11 and 9 bytes). The trailing `" A"` is the FTDI dual-channel suffix, i.e. channel A of an FT2232-class part. | [DLL]; chip identity [inferred] |
| Electrical link MCU<->FTDI | **8-bit parallel 245-style FIFO**, not a UART. Firmware drives VPORT0 (=PORTA) as the data bus, VPORT2 (=PORTF) bit 6 = WR#, bit 7 = RD#, VPORT1 (=PORTB) bit 6 = RXF#, bit 7 = TXE#, bit 1 = SIWU (pulsed after every packet). Write byte routine: `out 0x11,val; cbi 0x19,6; ...; ori 0xC0` (e.g. fw 0x4ca-0x4e6). Read: `cbi 0x19,7; in r24,0x12` (fw 0xf24-0xf2e). VPORT map set at fw 0x460: VPCTRLA=0x10, VPCTRLB=0x35. | [FW] |
| Baud rate / framing | **None.** The DLL never calls FT_SetBaudRate or FT_SetDataCharacteristics (import table has ordinals 1,2,3,4,6,9,16,18,19,29,70,72 only). The FIFO has no serial framing. | [FW+DLL] |
| Flow control | `FT_SetFlowControl(h, FT_FLOW_NONE=0, 0, 0)` (`connectSADI` @0x6d8822ad). Hardware handshake is the FIFO's RXF#/TXE#. | [DLL] |
| Latency timer | `FT_SetLatencyTimer(h, 2)` -- the `latency` argument of `momLab_connect(idx, latency)` is **ignored**; `momLab_connect` @0x6d881511 hard-codes 2 before calling `connectSADI`. | [DLL] |
| D2XX timeouts | Never set (FT_SetTimeouts not imported); reads are non-blocking because the DLL always reads exactly `FT_GetQueueStatus` bytes. | [DLL] |
| Open sequence | `CreateEventA` -> `FT_Open(devIndex)` -> `FT_Purge(RX|TX=3)` -> `FT_ResetDevice` -> `FT_SetFlowControl(0)` -> `FT_SetLatencyTimer(2)` -> `FT_Purge(3)` -> host state := 2 -> `FT_SetEventNotification(h, FT_EVENT_RXCHAR=1, hEvent)` (`connectSADI` @0x6d8821c0-0x6d882400). Then `momLab_connect` purges once more. | [DLL] |
| Close | `FT_Purge(3)`, `FT_Close`; host state := 0 (or 4 on close failure) (`closeSADI` @0x6d882530). | [DLL] |
| RX saturation | If `FT_GetQueueStatus` reports > 4096 bytes, the DLL prints "Saturation detected", does `FT_Purge(RX=1)`, resets its ring buffer and returns -2 (`getPacket` @0x6d882ac7). | [DLL] |
| Throughput | 612-byte packets at 1000/s = 612 kB/s sustained in Run state. This exceeds what an FT245R can do, consistent with an FT2232H/FT232H-class high-speed FIFO. | [FW] rate, chip [inferred] |
| MCU clock | 32 MHz internal RC with DFLL (OSC.CTRL|=0x06, CLK.CTRL=1, DFLLRC32M.CTRL=1; fw 0x23e-0x282). | [FW] |

---

## 2. Host -> device command packet (v1.003)

Fixed **62 bytes**, no length field, **no checksum/CRC**.

```
offset  size  value
0       1     0x55                      sync
1       1     opcode (1..4, below)
2..57   56    payload (zero except for Start)
58..61  4     AA 55 AA 55               tail (tailAppend @0x6d883280)
```

Opcodes (DLL `sendStart/sendStop/sendReset/sendQuery` write the 16-bit
little-endian word `0x01 55`, `0x02 55`, `0x03 55`, `0x04 55` at offset 0,
i.e. byte0=0x55, byte1=opcode) [DLL]; firmware dispatch on `rxbuf[1]` at
fw 0xff4-0x101a [FW]:

| opcode | name | payload | firmware action [FW] | DLL wait condition [DLL] |
|---|---|---|---|---|
| 1 | Start | bytes 2..5 = ADS8688 range code for ADC ch0..ch3 | ADS8688 `RST` (0x8500), ~1 ms, write range regs 0x05..0x08 with payload bytes, ~1 ms, `AUTO_RST` (0xA000), zero msgCount, state := 3, start TCD1 (fw 0x1020-0x11a2). **No explicit ack**; the first data packet carries state 3. | `momLab_Start` loops until state == 3 |
| 2 | Stop | none | state := 2, TCD1 stopped and CNT cleared, run LED off, then sends the Stop-ack packet (fw 0xff4-0x1012, packet builder 0x67e). | `momLab_Stop` loops until state == 2 |
| 3 | Reset | none | `RST.CTRL = SWRST` under CCP -> full MCU reboot; no reply before reset (fw 0x11a4-0x11b6). After reboot the firmware sends the boot/version packet with state 1. | `momLab_SendReset` loops until state == 1 |
| 4 | Query | none | Sends the version packet with the current state (fw 0x11b8-0x11c2, builder 0x4c2). | `momLab_query` clears host state to 0, then loops until state != 0 |

Firmware RX parser [FW] (main loop 0xf10-0xfb0): bytes are read one at a time
while RXF# is low. Outside a packet any byte other than 0x55 is discarded.
After 0x55, 61 more bytes are collected into `rxbuf[0..61]`; the packet is
accepted only if `rxbuf[58..61] == AA 55 AA 55` (checked at 0xfc2-0xfe6). On a
tail mismatch the firmware rescans the buffer for another 0x55 and shifts the
remainder down (0x11c4-0x122e) [inferred detail]. Opcodes 0 and >4 are ignored.

Example bytes (see vectors `host_to_device`):

```
Query : 55 04 00*56 AA 55 AA 55
Reset : 55 03 00*56 AA 55 AA 55
Stop  : 55 02 00*56 AA 55 AA 55
Start : 55 01 01 01 01 01 00*52 AA 55 AA 55     (all channels +-5.12 V)
```

### 2.1 Retry / timeout semantics in momLab.dll [DLL]

`momLab_query/SendReset/Start/Stop(int inst, double a, double b)`:

- `a` = **retry interval in milliseconds** (compared against
  `(now - lastSend) * 1000 / perfFreq`), `b` = **total timeout in seconds**
  (compared against `(now - start) / perfFreq`). E.g. `momLab_Start(0,20,1)`
  re-sends Start every 20 ms and gives up after 1 s. The source comment "2 ms
  retry" matches `momLab_Stop(0,2.0,1)`.
- Return 0 on success, 1 on timeout (prints "<cmd> timed out").
- `SendReset`, `Start`, `Stop` return 0 **immediately without sending** if the
  host-side state already equals the target (1, 3, 2 respectively)
  (@0x6d8817cd, 0x6d88193d, 0x6d881aad). `query` always sends because it zeroes
  the state first (@0x6d881657).
- The loop is a busy loop calling `getPacket` (no Sleep).

### 2.2 setAdcRange [DLL]

`momLab_setAdcRange(inst, ch, range)` (`setAdcRange` @0x6d882d30): returns 1 if
`ch > 3`, 2 if `range > 15` or `(1<<range) & 0x88EF == 0`, else stores the byte
in `SADI[inst].adcRange[ch]` and returns 0. Accepted codes:
{0,1,2,3,5,6,7,11,15}. Default after connect: 1 for all channels
(@0x6d88237a). The value is sent to the device only inside the next Start
packet; the device never echoes it, so the host must remember it for decoding.

---

## 3. Device -> host packets (v1.003)

All device packets are **612 bytes** (0x264), no length field, **no CRC**:

```
offset  size  field
0       1     0x55 sync
1       1     type: 4 = version/boot, 5 = data, 2 = Stop ack
2       1     device state (1 booted, 2 stopped, 3 running)
3       1     digital inputs (type 5: PORTD input byte); 0 otherwise
4..7    4     msgCount, uint32 little-endian (type 5); 0 otherwise
8..607  600   payload (see below)
608..611 4    AA 55 AA 55 tail
```

DLL framing (`getPacket` @0x6d882600): reads all queued bytes into a 4096-byte
ring, then scans for a byte 0x55 at index i such that bytes i+608..i+611 are
`AA 55 AA 55` (`tailCheck` @0x6d883250). Bytes before the match are dropped;
exactly one packet is consumed per `momLab_Read` call; the remainder is moved
to the start of the ring. Returns 0 on a decoded packet, -5 if fewer than 612
bytes are buffered or no match, -2 on saturation, else the FT status.
Only `byte[1]` selects the decode branch; every packet updates the host state
from `byte[2]` (@0x6d882815-0x6d882825).

### 3.1 Type 4 -- boot / version packet

Firmware builder @0x4c2 [FW]; emitted once after every boot (fw 0xf04) and in
reply to Query:

```
55 04 <state> 00  00 00 00 00  00 01 00 03  <596 x 00>  AA 55 AA 55
```

Bytes 8..9 = major (big-endian), 10..11 = minor (big-endian). Firmware
constants at 0x58c/0x5c6: `01`, `03` -> version 1.003. DLL
(@0x6d882a7f): `fwVersion = BE16[8..9] + BE16[10..11] / 1000.0`, stored as a
double and returned by `momLab_getFwVersion`. `momLab_getSwVersion` returns the
constant 1.003 (@0x6d8860c8). [FW+DLL]

### 3.2 Type 2 -- Stop acknowledge

Firmware builder @0x67e [FW]: `55 02 <state=2> 00` + 604 zero bytes +
`AA 55 AA 55`. The DLL has no special branch; it just takes state from byte 2.

### 3.3 Type 5 -- data packet (streamed in Run state)

Payload = **50 samples x 12 bytes**:

```
sample k at payload offset 12*k (absolute 8+12*k):
  +0..3   encoder position, int32 little-endian
  +4..5   ADC ch0, uint16 big-endian (raw ADS8688 code)
  +6..7   ADC ch1
  +8..9   ADC ch2
  +10..11 ADC ch3
```

[FW+DLL]: DLL decode loop @0x6d8828f6-0x6d8829c8 (encoder: `al=[p]; ah=[p+1];
|[p+2]<<16|[p+3]<<24`; ADC: `[p]<<8 | [p+1]`). Firmware TCD1 overflow ISR
@0x79c emits, per 20 us tick, exactly 12 bytes in this order (header + first
encoder on tick 0; four ADC words, encoder, three ADC words on tick 1; one ADC
word, encoder, three ADC words on ticks 2..49; the tail after the 50th tick).
Each ADC word is bytes 2..3 of a 32-bit SPI frame DMA'd from USARTF0 (the
ADS8688 returns the result in the upper half of the frame).

- **Encoder**: low 16 bits = TCC0.CNT (hardware quadrature decoder on PE2/PE3
  via EVSYS CH2, QDEN, 2-sample digital filter, pull-ups; fw 0xe96-0xec2),
  high 16 bits = software overflow/underflow counter maintained by the TCC0
  OVF ISR @0x420 (direction from TCC0.CTRLFSET bit 0). One encoder only, no
  index. 4x decoding (TC QDEC). [FW]
- **Digital inputs** byte 3 = `VPORT3.IN` = PORTD pins 0..7 (fw 0x836). The DLL
  stores it and returns it from `momLab_readPort`. [FW+DLL]
- **msgCount**: incremented once per packet, zeroed on Start (fw 0x1180) and at
  boot; `momLab_getMsgCount` returns it. Little-endian (adiw on byte 0x22B1,
  adc into 0x22B3/0x22B4). [FW+DLL]
- **Sample rate**: TCD1 PER = 0x027F = 639, prescaler 1, F_CPU 32 MHz ->
  **50.000 kHz** per sample, 50 samples -> **1000 packets/s**. [FW]
- **Timestamp**: none. Time = msgCount*50 + k samples at 50 kHz. [FW]
- **ADC**: TI ADS8688-family (ADS8684 likely, 4 channels), 16-bit, SPI via
  USARTF0 in master-SPI mode at fPER/2 = 16 MHz, CS on PORTF0, auto-scan mode
  (`AUTO_RST`), four frames per sample. [FW] chip identity [inferred from the
  command set 0x8500/0xA000 and the register map 0x05..0x08]

### 3.4 Interleaving hazards [inferred from FW]

- Stop stops TCD1 immediately, so a partially emitted data packet is truncated
  and immediately followed by the Stop-ack. The DLL resync scan skips the
  fragment (vector `truncated_data_packet_then_stop_ack`).
- The ISR phase counter (RAM 0x2006) is **not** reset by Stop or Start, so the
  first bytes after a restart may be the remainder of an old packet without a
  header; the DLL discards them.
- A Query during Run inserts a version packet between data packets (the main
  loop writes to the same FIFO while the ISR is active). Both parsers tolerate
  this only because the ISR is not re-entrant with respect to the main loop
  byte writes -- the exact interleaving is **[unverified]**.

---

## 4. ADC range codes and raw -> volts (v1.003)

The range byte is written verbatim into the ADS8688 per-channel range register
(fw 0x10c0-0x10e4) [FW], so the enum is the ADS8688 code set. The DLL's jump
table @0x6d8863fc and constants @0x6d886448..0x6d886470 give the scaling
[DLL]. The two sources agree on which codes exist [FW+DLL]:

| code | enum name (example_main.c style) | range | DLL branch | full-scale const |
|---|---|---|---|---|
| 0 | Range_pm_10_24 | +-10.24 V | 0x6d882a40 | 10.24 |
| 1 | Range_pm_05_12 | +-5.12 V (default) | 0x6d882a50 | 5.12 |
| 2 | Range_pm_02_56 | +-2.56 V | 0x6d8829e0 | 2.56 |
| 3 | Range_pm_01_28 | +-1.28 V | 0x6d882a20 | 1.28 |
| 11 | Range_pm_00_64 | +-0.64 V | 0x6d882a70 | 0.64 |
| 5 | Range_0_10_24 | 0..10.24 V | 0x6d882a10 | 10.24 |
| 6 | Range_0_05_12 | 0..5.12 V | 0x6d882a30 | 5.12 |
| 7 | Range_0_02_56 | 0..2.56 V | 0x6d882972 | 2.56 |
| 15 | Range_0_01_28 | 0..1.28 V | 0x6d882a60 | 1.28 |

Codes 4,8,9,10,12,13,14 are rejected by `setAdcRange`; their jump-table slots
point to a garbage path (0x6d8829f4). `example_main.c` uses
`Range_pm_05_12`, and the compiled demo inside the DLL passes 1 for the same
call, so `Range_pm_05_12 == 1` [DLL].

DLL conversion (@0x6d882982-0x6d8829aa), with `raw` the big-endian 16-bit
word and `div4` = C `int16 / 4` (truncation toward zero):

```
bipolar  (0,1,2,3,11): int14 = div4( (int16)(raw + 0x7FFF) )
                       volts = int14 * FS / 8191.0
unipolar (5,6,7,15):   int14 = div4( (int16)raw )
                       volts = int14 * FS / 16383.0
```

`int14` is stored in `SADI[i].adcIntData[ch][k]` (int16, offset 0x658),
`volts` in `adcVoltage[ch][k]` (double, offset 0x18); `momLab_GetVoltage(inst,
ch, k)` returns the latter (k >= 50 reads sample 0).

Known DLL quirks (the Rust codec should expose a bug-compatible mode and an
"ideal" mode; the vectors carry both `volts_dll` and `volts_ideal`):

- Bipolar: the offset should be 0x8000, not 0x7FFF. Result: raw 0x0000
  (input <= -FS) decodes to **+FS** instead of -FS; every other code is off by
  one LSB16 before the /4, which is below the 14-bit resolution.
- Unipolar: `raw` is treated as signed, so codes >= 0x8000 (upper half of the
  range) decode **negative**, and the divisor 16383 halves the scale. Per the
  ADS8688 datasheet the straight-binary conversion is `raw / 65535 * FS`.
  **[unverified on hardware]** -- the vendor may have relied on never using
  unipolar codes (the demo only uses 1).

The "14-bit" resolution advertised by the vendor is the DLL throwing away the
two LSBs of a 16-bit converter.

---

## 5. State machine (v1.003)

Device state byte (RAM 0x22B0) [FW]: **1** = booted (set in init @0xe52),
**2** = stopped (Stop handler), **3** = running (Start handler). No other
values exist in this firmware.

Host-side `SADI[i].state` (offset 0x18c8) [DLL]: 0 after `momLab_query`
starts, after close, and after `connectSADI` begins; **2** is assumed right
after a successful open (before any device traffic!) @0x6d882327; **4** if
`FT_Close` fails; otherwise it mirrors the last received `byte[2]`.
`momLab_getState` calls `getPacket` once and returns the value.
`momLab_queryBoot(inst)`: returns -1 if fewer than 128 bytes are queued
(`momLab_isBufferReady(inst,2)` is true when `queued < n*64`), else reads a
packet; returns 0 and clears state if state != 0, else -2.

Mapping to the vendor LIB 3.0 names (for naming only; v1.003 has no Init/Setup
phase because configuration rides in Start):

| LIB 3.0 name | v1.003 equivalent |
|---|---|
| Opened_state (1) | host just opened; device state unknown (host assumes 2) |
| Ready_state (2) | device 1 (after reset/boot) or 2 (after stop) |
| InitSent/Setup (4/3) | not present; ranges are sent inside Start |
| Start_initiated (5) | host sent Start, waiting for a packet with state 3 |
| Run_state (6) | device 3 |
| StopInitiated (7) | host sent Stop, waiting for state 2 |
| Stopped_state (8) | device 2 |
| Error_state (9) | host 4 (close failure) / FT errors |

Recommended host sequence (from `example_main.c` and `dllDemo` @0x6d882fb0):
open -> Query (retry 200 ms, timeout 2 s) -> Reset (retry 200 ms, 2 s; waits
for boot packet with state 1) -> Query (confirms state 1, refreshes version) ->
read fwVersion -> set ranges -> Start (retry 20 ms, 1 s) -> loop `momLab_Read`
until desired msgCount -> Stop (retry 2 ms, 1 s) -> close.

Boot handshake [FW]: on power-up or SWRST the firmware configures clocks,
blinks the boot LEDs while PB4 is high (0x47e), initialises the FIFO port,
ADC-SPI, encoder decoder and timer, sends the type-4 packet (state 1, version
1.003) once, then enters the command loop. There is no "ready request"
needed: the DLL just waits for that packet (or asks for it again with Query).

---

## 6. Version numbers

- Firmware: bytes 8..11 of the type-4 packet, two big-endian uint16 (major,
  minor/1000): `00 01 00 03` -> 1.003. [FW+DLL]
- DLL: constant double 1.003 at 0x6d8860c8 returned by `momLab_getSwVersion`.
  [DLL]
- The firmware file name `SADI_MOM_v1.003` matches the embedded constant.

---

## 7. Host data model exposed by momLab.dll (for API parity) [DLL]

`SADI[16]` array of 0x18d0-byte structs at 0x6d889460:

| offset | field |
|---|---|
| 0x000 | FT_HANDLE |
| 0x004 | FTDI device index (byte; 0xFF = none) |
| 0x008 | double fwVersion |
| 0x010 | uint8 adcRange[4] |
| 0x014 | uint32 msgCount |
| 0x018 | double adcVoltage[4][50] |
| 0x658 | int16 adcIntData[4][50] |
| 0x7e8 | int32 encoder[50] |
| 0x8b0 | uint8 digitalInputs |
| 0x8b1 | uint8 rxRing[4096] |
| 0x18b4/0x18bc/0x18c0 | write / read / end pointers |
| 0x18c4 | uint16 buffered length |
| 0x18c8 | int state |

`momLab_GetEncoder(inst, k)` returns `encoder[k]` (k >= 50 -> 0).
`momLab_startTimer` / `timeSinceTimerStart_uS/_mS` are QueryPerformanceCounter
helpers unrelated to the wire protocol.

---

## 8. Secondary target: firmware 3.41HS with SADI_FW3.dll

(See section 9 for the version diff.)

`SADI_FW3.dll` is stripped (exports only, image base 0x65300000); its internal
constant `getDllVersionNumber` = **3.021** (@0x65307420), so it predates the
vendor "LIB 3.0 reference" text slightly but matches firmware 3.41 on every
point that could be cross-checked. Firmware 3.41 is 11920 bytes, same MCU and
clock (32 MHz), same FIFO wiring except VPORT3 = PORTC (VPCTRLB=0x25 @0x266).

### 8.1 Transport [FW+DLL]

Parallel 245 FIFO again; no baud, no UART. DLL open sequence
(`openSADI_LV` -> 0x65301a80): `FT_Open`, `FT_ResetDevice`,
`FT_SetBitMode(h, 0x40, 0x00)` (mask 0x40, mode 0 = reset to EEPROM mode),
`FT_Purge(3)`. No latency timer, no flow-control, no event notification. Device
discovery via `FT_ListDevices(FT_LIST_ALL|FT_OPEN_BY_DESCRIPTION)` and exact
9-byte `strncmp` against `"SADI 2.0"`: **"SADI 2.0 A" is not matched** by this
DLL. Firmware TX now goes through a RAM ring drained by a PORTB_INT0 (TXE#)
ISR @0x4f4; RX bytes are pulled by PORTB_INT1 ISR @0x5ca and by polling.

### 8.2 Framing and CRC [FW+DLL]

```
55 <opcode> <payload...> <crc_hi> <crc_lo>
```

No tail bytes. Length is fixed **per opcode** (firmware table 0x2182-0x2270,
DLL 0x65303xxx parser phase 1). CRC-16 over every preceding byte, poly 0x1021,
init 0xFFFF, no reflection, no xor-out (CRC-16/CCITT-FALSE; check value of
"123456789" = 0x29B1), stored big-endian. Firmware uses the XMEGA CRC module
(CRC.CTRL reset bits 11 = all-ones init, CRC16 mode; feeds all bytes including
the received CRC and accepts iff CHECKSUM0/1 == 0, @0x1fd6/0x2274). DLL builds a
table @0x65303d20, appends @0x65303db0, verifies @0x65303e40. Bad CRC: firmware
resets its parser and resyncs on the next 0x55; DLL `sadiMaintenance_LV`
returns 8.

### 8.3 Host -> device opcodes

| op | DLL function | len | payload | firmware 3.41 action |
|---|---|---|---|---|
| 0x94 | `requestReady_LV` @0x653023a0 | 4 | - | replies 0xF6 version packet (@0x25d0) [FW] |
| 0x92 | `requestInfo_LV` @0x65302760 | 4 | - | **not in firmware dispatch table; ignored** [FW]. The DLL expects the 0xF6 reply to come from 0x94 anyway. |
| 0xF3 | `sendReset_LV` @0x653025f0 | 4 | - | `RST.CTRL=SWRST` (@0x2002), no reply [FW]; DLL also re-inits its struct and purges |
| 0xF4 | `sendStart_LV` @0x65302680 | 4 | - | replies `55 F2 F4 01 crc` [FW]; DLL -> state 6 Run |
| 0xF5 | `sendStop_LV` @0x653026f0 | 4 | - | stops TCD1, zeroes AOUT0, replies `55 F2 F5 01 crc`, then **watchdog-resets itself** (WDT.CTRL=0xFD @0x1f7c) [FW]; DLL -> state 8 Stopped |
| 0x93 | `sendPredefInit_LV(inst, sel, freq)` @0x65302530 | 12 | [2..3] loop freq u16 LE, [4..5] selection u16 LE (2 pendulum, 3 MOM), [6..9] vendor ADC range codes ch0..3 | programs TCD1 from freq (PER = 32e6/f - 1, prescaler escalates for low f, @0xdba), remaps range codes through RAM table 0x220A and writes ADS8688 regs 5..8, sets device state 3, replies `55 F2 93 <state> crc` [FW] |
| 0x90 | `sendInit_LV` @0x65302410 | 36 | [2..3] loopFreq, [4..7] adcRange[4], [8..11] enc0 {pinLoc,index,abs,filter}, [12..15] enc0 resolution u32, [16..19] enc1 cfg, [20..23] enc1 res, [24..25] servoEnables, [26..27] servoFreq, [28..29] motorEnables, [30..31] motorFreq, [32..33] outputPinMsk [DLL] | handler @0x25b4: sets TCD1 from freq, state 2, replies `55 F2 93 <state> crc`; detailed field consumption by 0x1840 **[unverified]** |
| 0x63 | `sendWrite_LV` @0x653027d0 | 30 (mode 1) / 8 (mode 2,3) | mode 1: [2..3] AOUT0, [4..5] AOUT1, [6..13] motor[4], [14..21] servo[4], [22..23] OutSET, [24..25] OutCLR, [26..27] OutTGL; mode 2/3: [2] 0, [3] motorDir, [4..5] value | firmware picks the 8-byte form when its state is 2/3 and the 30-byte form in state 1 (@0x2232); the 8-byte write clamps to 0x3FF and drives TCC1 CCA/CCB (motor PWM) [FW]; DAC writes via DACB CH0/CH1DATA [FW] |

Host-side validation (DLL): `setupADC_LV` accepts range codes 0..5 and
9..13; `setupEncoder_LV` pinLoc in {0..5,8..10}, filter <= 7, index not allowed
on 6/10; `setupServoPWM/MotorPWM` 4-bit masks; `setupOutputPinMsk` 12-bit.

### 8.4 Device -> host packets

| op | len | layout | handling |
|---|---|---|---|
| 0xF6 | 8 | `55 F6 <float32 LE version> crc` ; firmware bytes `71 3D 5A 40` = **3.41** (@0x2616) | DLL `infoHandler_LV`: only in state 1 (Opened): store version, state := 2 Ready [FW+DLL] |
| 0xF2 | 6 | `55 F2 <echoed op> <status> crc` | DLL: F4/1 -> Run(6); F5/1 -> Stopped(8); 93/2 -> Setup "Pendulum Mode", 93/3 -> Setup "MOM Mode"; 91/1 -> Setup(3) [DLL]; firmware emits F4/1, F5/1, 93/state [FW] |
| 0x91 | 64 | init echo compared against the sent config; mismatch -> state 9 | **DLL only**; firmware 3.41 never emits 0x91 [FW] |
| 0x61 | 30 | data, below | `inputSuperPacketBufferPush_LV` ring of 256 packets; `getDataLatest` pops newest [DLL] |

Data packet (firmware TCD1 ISR @0xe22, one sample per tick) [FW], offsets
confirmed by the DLL mode-1 extractors [DLL]:

```
0      55
1      61
2..9   ADC ch0..ch3, uint16 LITTLE-endian (ADS8688 raw code)
10..13 encoder 0, int32 LE  (TCE1.CNT + software high word @0x2397)
14..15 TCC0.CCA, uint16 LE  (input capture)
16..19 encoder 1, int32 LE  (TCC1.CNT + high word @0x239B)
20..21 TCF0.CCA, uint16 LE  (encoder period -> "velocity")
22     PORTE.IN & 0x0F        } DLL: inputs12 = (b22<<8 | b23) & 0xFFF
23     PORTD.IN               }
24..27 msgCNT uint32 LE (per tick)
28..29 CRC-16 (big-endian)
```

No state byte in data packets. Sample rate = programmed loop frequency.
The DLL has alternative 16-byte decodes for modes 2/3 (ENCPos at [4..7],
inputCapture at [2..3], velocity/msgCNT at [8..]) which the firmware 3.41
disassembly did **not** show being emitted; treat as [unverified].

### 8.5 ADC codes and scaling (v3) [FW+DLL]

Vendor codes (as in the LIB 3.0 text) are remapped by the firmware
(RAM table 0x220A, index code-2; out-of-range codes incl. 0 and 1 give 0):

| vendor code | range | ADS8688 code written |
|---|---|---|
| 0 | OFF (DLL returns 0.0 V) | 0 |
| 1 | +-10.24 | 0 |
| 2 | +-5.12 | 1 |
| 3 | +-2.56 | 2 |
| 4 | +-1.28 | 3 |
| 5 | +-0.64 | 11 |
| 9 | 0..10.24 | 5 |
| 10 | 0..5.12 | 6 |
| 11 | 0..2.56 | 7 |
| 12 | 0..1.28 | 15 |

DLL (`extractFromInputPacket_ADC` @0x65302ca0, `convertToVoltage`
@0x65303a00): bipolar (code <= 8): `int14 = div4((int16)(raw + 0x7FFF))`,
`V = int14 * FS / 8191`; unipolar (code >= 9): `int14 = raw >> 2` (logical),
`V = int14 * FS / 16383`. Codes 6,7,8 and > 13 return NaN. So v3 fixes the
v1.003 unipolar sign bug but keeps the 0x7FFF offset quirk.
`convertToVelocity(count, resolution)` = `3.0 * count * resolution /
3141592.653589793` (constants @0x65307430/38) -- units [inferred].

### 8.6 State machine (v3) [DLL]

Host states 1..9 exactly as in the vendor text. Transitions are driven only
by received packets (0xF6 -> 2, 0xF2 acks -> 3/6/8, 0x91 mismatch -> 9); the
DLL has **no timeouts or retries**; `sadiMaintenance_LV` returns 5 (FT error),
6 (fewer than 3 bytes), 7 (unknown opcode), 8 (bad CRC) and the LabVIEW loop
re-calls it. Firmware device state (RAM 0x2608): 0 boot, 1 after 30-byte
0x63 init, 2 after 0x90, 3 after 0x93 [FW]. No unsolicited boot packet: the
host must send 0x94 to learn the version [FW].

---

## 9. Version diff: v1.003 (MOM) vs v3.41 (generic)

| Aspect | v1.003 MOM (lab board) | v3.41 generic | same? |
|---|---|---|---|
| Transport | FT245-style FIFO, desc "SADI 2.0 A"/"SADI 2.0", latency 2 ms | FIFO, DLL matches only "SADI 2.0", no latency setting | partly |
| Sync byte | 0x55 | 0x55 | yes |
| Command length | fixed 62 | per-opcode 4/8/12/30/36 | no |
| End marker | AA 55 AA 55 tail, no CRC | CRC-16/CCITT-FALSE BE, no tail | no |
| Opcodes | 1 Start, 2 Stop, 3 Reset, 4 Query | 0xF4 Start, 0xF5 Stop, 0xF3 Reset, 0x94 Ready/version, 0x93 PredefInit, 0x90 Init, 0x63 Write, (0x92 ignored) | no (not even the numbering) |
| Config path | ADC ranges inside Start (raw ADS8688 codes) | separate Init/PredefInit with vendor codes remapped by firmware; loop frequency programmable | no |
| Reply length | always 612 | 6 (ack) / 8 (version) / 30 (data) | no |
| Version packet | type 4: BE major, BE minor/1000 (`00 01 00 03`), sent unsolicited at boot and on Query | 0xF6: float32 LE (`71 3D 5A 40`), only on request 0x94 | no |
| Ack packets | none for Start (state in data), Stop ack = 612-byte type 2 | `55 F2 <op> <status> crc` for Start/Stop/Init | no |
| Data packet | 50 samples x (enc i32 LE + 4 x ADC **BE**), state byte, PORTD byte, msgCount per packet, fixed 50 kHz | 1 sample: 4 x ADC **LE**, 2 encoders, capture, velocity, 12 input bits, msgCNT per sample, CRC, programmable rate | no |
| ADC chip/SPI | ADS8688-family via USARTF0, AUTO_RST scan | same chip, manual channel commands C0/C4/C8/CC | chip yes |
| Encoder | 1 x TCC0 QDEC + sw high word | 2 x (TCE1, TCC1) QDEC + sw high words, plus capture timers | no |
| Reset | SWRST on opcode 3, boot packet follows | SWRST on 0xF3 (silent); Stop also self-resets via WDT | partly |
| State codes on wire | 1 booted / 2 stopped / 3 running | ack status bytes; device state 0..3 internal | no |
| Scaling | int14 = div4(raw+0x7FFF) (bipolar), signed raw>>2 (unipolar, buggy) | same bipolar quirk; unipolar logical shift (correct) | partly |

Compatibility:

- `momLab.dll` with firmware 3.41: every 62-byte command fails the firmware
  CRC and is dropped; nothing the firmware sends has the AA 55 AA 55 tail at
  offset 608, so the DLL never decodes a packet. **Incompatible.** [FW+DLL]
- `SADI_FW3.dll` with firmware 1.003: its 4-byte commands lack the tail at
  bytes 58..61 and are discarded (the 0x55 at byte 0 starts a 62-byte
  collection that will fail the tail check); the 612-byte replies have opcodes
  4/5/2 which the DLL parser treats as unknown (return 7) and resyncs on the
  next 0x55 inside the data, never completing a CRC-valid packet.
  **Incompatible.** [FW+DLL]
- There is no version handshake that works across both: v1.003 announces
  itself unsolicited at boot (type 4 packet), v3.41 only answers 0x94. A Rust
  host wanting to auto-detect can: open, purge, send the v1.003 Query
  (62 bytes) and look for a 612-byte type-4 frame; if none within ~2 s, send
  the v3 0x94 and look for an 8-byte 0xF6 frame. Firmware 1.003 ignores the
  4-byte frame harmlessly (tail check fails, resync); firmware 3.41 drops the
  62-byte frame on CRC. [inferred]
- A 62-byte v1.003 command happens to start `55 01..04`; firmware 3.41 does
  not know opcodes 1..4 and ignores them (after reading the implied length it
  resyncs). Conversely v3 opcodes 0x90..0xF5 are ignored by firmware 1.003.
  Neither firmware can be bricked or mis-configured by the other's commands
  **as far as the disassembly shows** [inferred].
- The LabVIEW VIs in the vendor LVLib (momLab.lvlib) wrap momLab.dll; the
  `SADI+LVLib` package wraps SADI_FW3.dll. Use the right pair for the board.

What is shared and therefore reusable in the Rust crate: sync byte 0x55, the
FTDI FIFO transport layer, the ADS8688 raw-code model and the bipolar
conversion quirk, the little-endian int32 encoder (hardware CNT + software
high word) and the general host loop shape (send command, parse frames,
update state from frames).

---

## 10. What can only be confirmed with the physical board

v1.003 (primary):

1. FTDI part and mode: that the "SADI 2.0 A" device really is an FT2232H
   channel in 245 FIFO mode and that 612 kB/s streams without
   "Saturation detected" purges at latency 2 ms.
2. The actual ADC part (ADS8684 vs ADS8688) and therefore whether auto-scan
   really cycles only four channels; a wrong assumption would show up as
   channel data alternating between two sets.
3. Real voltage scaling for unipolar codes 5/6/7/15 and the behaviour at the
   bipolar extremes (the DLL formulas look wrong; the board tells which to
   implement).
4. Encoder sign convention (which of PE2/PE3 is A/B) and that the high word
   from the overflow ISR is contiguous with TCC0.CNT (PER left at 0xFFFF).
5. Whether the firmware ever emits anything else (e.g. after a bad command
   tail), and the exact byte interleaving when Query/Stop arrive mid-packet.
6. Boot time after Reset (the LED-blink loop at 0x47e depends on the PB4 pin
   level) and therefore sensible retry/timeout values.
7. Digital-input byte pin mapping (PORTD bit n -> connector pin) and polarity.
8. Whether the firmware tolerates back-to-back commands (the DLL re-sends a
   command every `a` ms until the state changes; duplicates of Start re-run
   the ADS8688 reset sequence).

v3.41 (secondary):

9. The CRC init value (0xFFFF inferred from CRC.CTRL reset=11) and that
   `55 94 2F 78` really elicits `55 F6 71 3D 5A 40 D5 D3`.
10. Whether a 16-byte MOM-mode data packet exists (DLL decodes one, firmware
    disassembly shows only the 30-byte form) and the exact 0x90/0x63 field
    consumption by the firmware.
11. Whether Stop's watchdog self-reset is intentional and how long the board
    is silent afterwards.
