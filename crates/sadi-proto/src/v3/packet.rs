//! v3.41 device packets (0xF6 version, 0xF2 ack, 0x61 data).

use super::opcode::{DeviceOpcode, HostOpcode};
use super::{unseal, V3Error};

/// 0xF6 version reply carrying the firmware version.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct VersionPacket {
    /// Firmware version (float32 LE on the wire, 3.41 for the target).
    pub fw_version: f32,
}

/// 0xF2 acknowledge of a host command.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AckPacket {
    /// Opcode of the command being acknowledged.
    pub echoed: HostOpcode,
    /// Status byte (for 0x93: device state 2 pendulum / 3 MOM; for F4/F5: 1).
    pub status: u8,
}

/// 0x61 data packet: one sample per tick.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DataPacket {
    /// Raw ADS8688 codes for channels 0..3.
    pub adc_raw: [u16; 4],
    /// Encoder 0 count.
    pub encoder0: i32,
    /// Input-capture counter (TCC0.CCA).
    pub input_capture: u16,
    /// Encoder 1 count.
    pub encoder1: i32,
    /// Encoder period value, the DLL's "velocity".
    pub encoder_velocity: u16,
    /// 12 digital inputs, `(b22 << 8 | b23) & 0xFFF`.
    pub inputs_12bit: u16,
    /// Per-tick message counter.
    pub msg_count: u32,
}

/// A decoded device-to-host packet.
#[derive(Debug, Clone, Copy, PartialEq)]
#[non_exhaustive]
pub enum Packet {
    /// 0xF6.
    Version(VersionPacket),
    /// 0xF2.
    Ack(AckPacket),
    /// 0x61.
    Data(DataPacket),
}

fn u16_at(b: &[u8], i: usize) -> u16 {
    u16::from_le_bytes([b[i], b[i + 1]])
}

fn u32_at(b: &[u8], i: usize) -> u32 {
    u32::from_le_bytes([b[i], b[i + 1], b[i + 2], b[i + 3]])
}

impl Packet {
    /// Decodes one complete frame, checking sync, length and CRC.
    pub fn decode(frame: &[u8]) -> Result<Self, V3Error> {
        let first = frame.get(1).copied().ok_or(V3Error::BadLength {
            expected: 4,
            actual: frame.len(),
        })?;
        let op = DeviceOpcode::try_from(first)?;
        if frame.len() != op.frame_len() {
            return Err(V3Error::BadLength {
                expected: op.frame_len(),
                actual: frame.len(),
            });
        }
        // `body` starts at the opcode, so frame offset n is body offset n - 1.
        let body = unseal(frame)?;
        let pkt = match op {
            DeviceOpcode::Version => Self::Version(VersionPacket {
                fw_version: f32::from_bits(u32_at(body, 1)),
            }),
            DeviceOpcode::Ack => Self::Ack(AckPacket {
                echoed: HostOpcode::try_from(body[1])?,
                status: body[2],
            }),
            DeviceOpcode::Data => Self::Data(DataPacket {
                adc_raw: [
                    u16_at(body, 1),
                    u16_at(body, 3),
                    u16_at(body, 5),
                    u16_at(body, 7),
                ],
                encoder0: u32_at(body, 9) as i32,
                input_capture: u16_at(body, 13),
                encoder1: u32_at(body, 15) as i32,
                encoder_velocity: u16_at(body, 19),
                inputs_12bit: ((u16::from(body[21]) << 8) | u16::from(body[22])) & 0xFFF,
                msg_count: u32_at(body, 23),
            }),
        };
        tracing::debug!(opcode = ?op, "v3 decoded packet");
        Ok(pkt)
    }
}
