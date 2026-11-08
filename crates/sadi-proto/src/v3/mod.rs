//! Optional firmware 3.41 codec: CRC-16/CCITT-FALSE framed commands and packets.
//!
//! Secondary target (docs/protocol.md section 8); items 9-11 of section 10 stay
//! unverified until a hardware session. Pure functions, no I/O, never panics on input.
#![forbid(unsafe_code)]

pub mod command;
pub mod crc;
pub mod opcode;
pub mod packet;

pub use command::{Command, InitMode, VendorRange};
pub use crc::{crc16, CRC_CHECK_VALUE};
pub use opcode::{DeviceOpcode, HostOpcode};
pub use packet::{AckPacket, DataPacket, Packet, VersionPacket};

use crate::error::ProtoError;

/// Sync byte that starts every v3.41 frame.
pub const SYNC: u8 = 0x55;

/// Failures raised while encoding or decoding v3.41 frames.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[non_exhaustive]
pub enum V3Error {
    /// A frame had the wrong number of bytes for its opcode.
    #[error("bad frame length: expected {expected}, got {actual}")]
    BadLength {
        /// Required length in bytes.
        expected: usize,
        /// Length actually supplied.
        actual: usize,
    },
    /// A frame did not start with the 0x55 sync byte.
    #[error("bad sync byte 0x{0:02x}")]
    BadSync(u8),
    /// The trailing CRC did not match the preceding bytes.
    #[error("bad crc: expected 0x{expected:04x}, got 0x{actual:04x}")]
    BadCrc {
        /// CRC computed over the received bytes.
        expected: u16,
        /// CRC carried in the frame.
        actual: u16,
    },
    /// An opcode that is not part of the v3.41 command set.
    #[error("unknown host opcode 0x{0:02x}")]
    UnknownHostOpcode(u8),
    /// An opcode that is not a known device packet.
    #[error("unknown device opcode 0x{0:02x}")]
    UnknownDeviceOpcode(u8),
    /// A vendor ADC range code outside {0..=5, 9..=12}.
    #[error("invalid vendor range code {0}")]
    InvalidRange(u8),
    /// A predefined-init selection other than 2 (pendulum) or 3 (MOM).
    #[error("invalid init selection {0}")]
    InvalidSelection(u16),
}

impl From<V3Error> for ProtoError {
    /// Maps a v3 codec failure onto the crate-wide malformed-packet error.
    fn from(e: V3Error) -> Self {
        ProtoError::Malformed(e.to_string())
    }
}

/// Appends the big-endian CRC to `body` and returns the finished frame.
pub(crate) fn seal(mut body: Vec<u8>) -> Vec<u8> {
    let c = crc16(&body);
    body.extend_from_slice(&c.to_be_bytes());
    body
}

/// Checks sync and CRC of a whole frame, returning the bytes between them.
pub(crate) fn unseal(frame: &[u8]) -> Result<&[u8], V3Error> {
    let [sync, .., _, _] = frame else {
        return Err(V3Error::BadLength {
            expected: 4,
            actual: frame.len(),
        });
    };
    if *sync != SYNC {
        tracing::warn!(sync = *sync, "v3 frame: bad sync");
        return Err(V3Error::BadSync(*sync));
    }
    let (body, tail) = frame.split_at(frame.len() - 2);
    let actual = u16::from_be_bytes([tail[0], tail[1]]);
    let expected = crc16(body);
    if expected != actual {
        tracing::warn!(expected, actual, "v3 frame: bad crc");
        return Err(V3Error::BadCrc { expected, actual });
    }
    Ok(&body[1..])
}
