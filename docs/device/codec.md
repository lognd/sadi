# sadi-proto codec (v1.003 MOM)
Status: draft

Owner: ticket ~80SB0TA. Source: `crates/sadi-proto/src/codec/`. The wire
format is unverified until a hardware session (protocol.md section 10),
so every unverified choice is an explicit switch, not a silent default.

## Commands (host to device, 62 bytes)
`Command::{Start, Stop, Reset, Query}.encode()` yields
`0x55, opcode, payload.., AA 55 AA 55` (tail at 58..61). Opcodes: 1
Start, 2 Stop, 3 Reset, 4 Query. Start carries four ADC range codes at
bytes 2..5. `AdcRange::from_code` accepts only {0,1,2,3,5,6,7,11,15};
others return `CodecError::InvalidRangeCode`. `Command::decode` is the
inverse (used by the simulator).

## Packets (device to host, 612 bytes)
`Packet::parse` handles type 4 (version: major/minor big-endian at
8..11), type 5 (data: 50 samples at 8+12k, i32 LE encoder then four u16
BE ADC words) and type 2 (stop ack). Header: state, digital byte,
msgCount u32 LE at 4..7. There is no CRC; the only integrity check is
the `AA 55 AA 55` tail at 608..611. Unknown types return
`CodecError::UnknownType`.

## ADC scaling: `AdcMode`
Selected explicitly per call (`convert`, `Sample::volts`).
- `DllCompatible`: bipolar `int14 = ((raw + 0x7FFF) as i16) / 4`, volts
  `int14 * FS / 8191`; unipolar `int14 = (raw as i16) / 4`, volts
  `int14 * FS / 16383`. Reproduces the vendor DLL.
- `Ideal`: bipolar `(raw - 32768) / 32768 * FS`; unipolar
  `raw / 65535 * FS`.
Both pass every `v1_003_mom.adc_conversion_cases` vector (volts to
1e-8, the precision stored in the file).

## Resync `Decoder`
`push(bytes)` then `next_packet()` / `drain()`. Like the DLL getPacket:
find `0x55`, require the tail at +608, otherwise drop one byte and
rescan. Malformed frames surface as `Err` items; the decoder never
panics on arbitrary input. `DecoderStats` counts packets, malformed
frames, dropped bytes, msgCount gap events and missed packets. A data
msgCount above last+1 is a gap; one at or below last is treated as a
device restart. Non-data packets reset gap tracking.

## Tests
`crates/sadi-proto/tests/vectors.rs` replays protocol-vectors.json
(commands, packets, ADC cases in both modes, framing cases), a
garbage/dropped-byte resync scenario and proptests (no panic on
arbitrary bytes; later intact packets always recovered).
