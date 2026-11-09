//! v3.41 host commands and their encoding.

use super::opcode::HostOpcode;
use super::{seal, unseal, V3Error, SYNC};

/// Vendor ADC range code, validated against {0..=5, 9..=12}.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VendorRange(u8);

impl VendorRange {
    /// Returns the raw vendor code.
    #[must_use]
    pub const fn code(self) -> u8 {
        self.0
    }
}

impl TryFrom<u8> for VendorRange {
    type Error = V3Error;

    /// Accepts only vendor codes the firmware remap table knows.
    fn try_from(c: u8) -> Result<Self, V3Error> {
        match c {
            0..=5 | 9..=12 => Ok(Self(c)),
            other => Err(V3Error::InvalidRange(other)),
        }
    }
}

/// Predefined-init selection (payload bytes 4..5).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum InitMode {
    /// Pendulum mode (2).
    Pendulum,
    /// MOM mode (3).
    Mom,
}

impl InitMode {
    /// Returns the wire selection value.
    #[must_use]
    pub const fn code(self) -> u16 {
        match self {
            Self::Pendulum => 2,
            Self::Mom => 3,
        }
    }
}

impl TryFrom<u16> for InitMode {
    type Error = V3Error;

    /// Parses a selection value; only 2 and 3 exist.
    fn try_from(v: u16) -> Result<Self, V3Error> {
        match v {
            2 => Ok(Self::Pendulum),
            3 => Ok(Self::Mom),
            other => Err(V3Error::InvalidSelection(other)),
        }
    }
}

/// A host-to-device command.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum Command {
    /// 0x94: ask for the version packet.
    RequestReady,
    /// 0xF3: software reset, no reply.
    Reset,
    /// 0xF4: start streaming.
    Start,
    /// 0xF5: stop streaming (device then resets itself).
    Stop,
    /// 0x93: predefined init.
    PredefInit {
        /// Loop frequency in Hz.
        loop_freq_hz: u16,
        /// Pendulum or MOM.
        mode: InitMode,
        /// Vendor range codes for ADC channels 0..3.
        ranges: [VendorRange; 4],
    },
}

impl Command {
    /// Returns the opcode of this command.
    #[must_use]
    pub const fn opcode(&self) -> HostOpcode {
        match self {
            Self::RequestReady => HostOpcode::RequestReady,
            Self::Reset => HostOpcode::Reset,
            Self::Start => HostOpcode::Start,
            Self::Stop => HostOpcode::Stop,
            Self::PredefInit { .. } => HostOpcode::PredefInit,
        }
    }

    /// Encodes the command as a complete CRC-sealed frame.
    #[must_use]
    pub fn encode(&self) -> Vec<u8> {
        let mut body = vec![SYNC, self.opcode().byte()];
        if let Self::PredefInit {
            loop_freq_hz,
            mode,
            ranges,
        } = self
        {
            body.extend_from_slice(&loop_freq_hz.to_le_bytes());
            body.extend_from_slice(&mode.code().to_le_bytes());
            body.extend(ranges.iter().map(|r| r.code()));
        }
        tracing::debug!(opcode = ?self.opcode(), "v3 encode command");
        seal(body)
    }

    /// Decodes a complete frame back into a command (inverse of [`Command::encode`]).
    pub fn decode(frame: &[u8]) -> Result<Self, V3Error> {
        let body = unseal(frame)?;
        let op = HostOpcode::try_from(body[0])?;
        if frame.len() != op.frame_len() {
            return Err(V3Error::BadLength {
                expected: op.frame_len(),
                actual: frame.len(),
            });
        }
        Ok(match op {
            HostOpcode::RequestReady => Self::RequestReady,
            HostOpcode::Reset => Self::Reset,
            HostOpcode::Start => Self::Start,
            HostOpcode::Stop => Self::Stop,
            HostOpcode::PredefInit => Self::PredefInit {
                loop_freq_hz: u16::from_le_bytes([body[1], body[2]]),
                mode: InitMode::try_from(u16::from_le_bytes([body[3], body[4]]))?,
                ranges: [
                    VendorRange::try_from(body[5])?,
                    VendorRange::try_from(body[6])?,
                    VendorRange::try_from(body[7])?,
                    VendorRange::try_from(body[8])?,
                ],
            },
        })
    }
}

#[cfg(test)]
mod code_tests {
    use super::*;

    // frob:tests crates/sadi-proto/src/v3/command.rs::VendorRange.code
    #[test]
    fn vendor_range_code() {
        assert_eq!(VendorRange::try_from(9).unwrap().code(), 9);
    }

    // frob:tests crates/sadi-proto/src/v3/command.rs::InitMode.code
    #[test]
    fn init_mode_code() {
        assert_eq!(InitMode::Pendulum.code(), 2);
        assert_eq!(InitMode::Mom.code(), 3);
    }

    // frob:tests crates/sadi-proto/src/v3/command.rs::Command.opcode
    #[test]
    fn command_opcode() {
        assert_eq!(Command::Start.opcode(), HostOpcode::Start);
        assert_eq!(Command::Stop.opcode(), HostOpcode::Stop);
        assert_eq!(Command::Reset.opcode(), HostOpcode::Reset);
        assert_eq!(Command::RequestReady.opcode(), HostOpcode::RequestReady);
        let r = VendorRange::try_from(0).unwrap();
        let c = Command::PredefInit {
            loop_freq_hz: 1,
            mode: InitMode::Mom,
            ranges: [r; 4],
        };
        assert_eq!(c.opcode(), HostOpcode::PredefInit);
    }
}
