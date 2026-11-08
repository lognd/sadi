//! v1.003 wire codec: host commands, device packets, ADC scaling, resync decoder.
//!
//! The wire format is UNVERIFIED until a hardware session (docs/protocol.md
//! section 10). Everything here is pure (no I/O) and never panics on input.
#![forbid(unsafe_code)]

pub mod adc;
pub mod command;
pub mod decoder;
pub mod packet;

pub use adc::{convert, dll_int14, AdcMode};
pub use command::{AdcRange, Command, COMMAND_LEN};
pub use decoder::{Decoder, DecoderStats};
pub use packet::{
    AdcChannel, DataPacket, DeviceState, InvalidChannel, Packet, Sample, StopAckPacket,
    VersionPacket, Volts, PACKET_LEN, SAMPLES_PER_PACKET,
};

use crate::error::ProtoError;

/// Sync byte that starts every command and every device packet.
pub const SYNC: u8 = 0x55;
/// Four-byte tail that ends every command and every device packet.
pub const TAIL: [u8; 4] = [0xAA, 0x55, 0xAA, 0x55];

/// Failures raised while encoding or decoding v1.003 frames.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
#[non_exhaustive]
pub enum CodecError {
    /// An ADC range code outside {0,1,2,3,5,6,7,11,15}.
    #[error("invalid ADC range code {0}")]
    InvalidRangeCode(u8),
    /// A frame had the wrong number of bytes.
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
    /// A frame did not end with AA 55 AA 55.
    #[error("bad tail {0:02x?}")]
    BadTail([u8; 4]),
    /// A device packet carried an unknown type byte.
    #[error("unknown packet type {0}")]
    UnknownType(u8),
    /// A host command carried an opcode outside 1..=4.
    #[error("unknown command opcode {0}")]
    UnknownOpcode(u8),
}

impl From<CodecError> for ProtoError {
    /// Maps a codec failure onto the crate-wide malformed-packet error.
    fn from(e: CodecError) -> Self {
        ProtoError::Malformed(e.to_string())
    }
}
