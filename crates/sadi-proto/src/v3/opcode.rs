//! Opcode enums for v3.41 frames, converted from raw bytes at the codec edge.

use super::V3Error;

/// Host-to-device opcodes implemented by this codec.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum HostOpcode {
    /// 0x93 sendPredefInit.
    PredefInit,
    /// 0x94 requestReady; elicits the 0xF6 version packet.
    RequestReady,
    /// 0xF3 sendReset.
    Reset,
    /// 0xF4 sendStart.
    Start,
    /// 0xF5 sendStop.
    Stop,
}

impl HostOpcode {
    /// Returns the wire byte.
    #[must_use]
    pub const fn byte(self) -> u8 {
        match self {
            Self::PredefInit => 0x93,
            Self::RequestReady => 0x94,
            Self::Reset => 0xF3,
            Self::Start => 0xF4,
            Self::Stop => 0xF5,
        }
    }

    /// Returns the total frame length for this opcode.
    #[must_use]
    pub const fn frame_len(self) -> usize {
        match self {
            Self::PredefInit => 12,
            Self::RequestReady | Self::Reset | Self::Start | Self::Stop => 4,
        }
    }
}

impl TryFrom<u8> for HostOpcode {
    type Error = V3Error;

    /// Parses a wire byte; unknown opcodes are an error.
    fn try_from(b: u8) -> Result<Self, V3Error> {
        match b {
            0x93 => Ok(Self::PredefInit),
            0x94 => Ok(Self::RequestReady),
            0xF3 => Ok(Self::Reset),
            0xF4 => Ok(Self::Start),
            0xF5 => Ok(Self::Stop),
            other => Err(V3Error::UnknownHostOpcode(other)),
        }
    }
}

/// Device-to-host opcodes implemented by this codec.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum DeviceOpcode {
    /// 0x61 data packet.
    Data,
    /// 0xF2 acknowledge.
    Ack,
    /// 0xF6 version packet.
    Version,
}

impl DeviceOpcode {
    /// Returns the wire byte.
    #[must_use]
    pub const fn byte(self) -> u8 {
        match self {
            Self::Data => 0x61,
            Self::Ack => 0xF2,
            Self::Version => 0xF6,
        }
    }

    /// Returns the total frame length for this opcode.
    #[must_use]
    pub const fn frame_len(self) -> usize {
        match self {
            Self::Data => 30,
            Self::Ack => 6,
            Self::Version => 8,
        }
    }
}

impl TryFrom<u8> for DeviceOpcode {
    type Error = V3Error;

    /// Parses a wire byte; unknown opcodes are an error.
    fn try_from(b: u8) -> Result<Self, V3Error> {
        match b {
            0x61 => Ok(Self::Data),
            0xF2 => Ok(Self::Ack),
            0xF6 => Ok(Self::Version),
            other => Err(V3Error::UnknownDeviceOpcode(other)),
        }
    }
}
