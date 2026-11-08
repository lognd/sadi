//! Host-to-device commands: the four fixed 62-byte frames.

use super::{CodecError, SYNC, TAIL};

/// Length in bytes of every host command frame.
pub const COMMAND_LEN: usize = 62;

/// ADS8688 input range code as accepted by momLab_setAdcRange.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AdcRange {
    /// Code 0: +-10.24 V.
    Pm10_24,
    /// Code 1: +-5.12 V (the power-on default).
    Pm5_12,
    /// Code 2: +-2.56 V.
    Pm2_56,
    /// Code 3: +-1.28 V.
    Pm1_28,
    /// Code 11: +-0.64 V.
    Pm0_64,
    /// Code 5: 0..10.24 V.
    Unipolar10_24,
    /// Code 6: 0..5.12 V.
    Unipolar5_12,
    /// Code 7: 0..2.56 V.
    Unipolar2_56,
    /// Code 15: 0..1.28 V.
    Unipolar1_28,
}

impl Default for AdcRange {
    /// Returns +-5.12 V, the range momLab.dll selects after connect.
    fn default() -> Self {
        AdcRange::Pm5_12
    }
}

impl AdcRange {
    /// Every valid range, in the order of protocol-vectors.json.
    pub const ALL: [AdcRange; 9] = [
        AdcRange::Pm10_24,
        AdcRange::Pm5_12,
        AdcRange::Pm2_56,
        AdcRange::Pm1_28,
        AdcRange::Unipolar10_24,
        AdcRange::Unipolar5_12,
        AdcRange::Unipolar2_56,
        AdcRange::Pm0_64,
        AdcRange::Unipolar1_28,
    ];

    /// Validates a wire code against {0,1,2,3,5,6,7,11,15}; same as `TryFrom<u8>`.
    pub fn from_code(code: u8) -> Result<Self, CodecError> {
        Self::try_from(code)
    }

    /// Returns the wire code written into the Start packet; same as `u8::from`.
    #[must_use]
    pub fn code(self) -> u8 {
        u8::from(self)
    }

    /// Returns the full-scale magnitude in volts.
    #[must_use]
    pub fn full_scale_volts(self) -> f64 {
        match self {
            AdcRange::Pm10_24 | AdcRange::Unipolar10_24 => 10.24,
            AdcRange::Pm5_12 | AdcRange::Unipolar5_12 => 5.12,
            AdcRange::Pm2_56 | AdcRange::Unipolar2_56 => 2.56,
            AdcRange::Pm1_28 | AdcRange::Unipolar1_28 => 1.28,
            AdcRange::Pm0_64 => 0.64,
        }
    }

    /// Returns true for the +-FS ranges, false for the 0..FS ranges.
    #[must_use]
    pub fn is_bipolar(self) -> bool {
        matches!(
            self,
            AdcRange::Pm10_24
                | AdcRange::Pm5_12
                | AdcRange::Pm2_56
                | AdcRange::Pm1_28
                | AdcRange::Pm0_64
        )
    }
}

impl TryFrom<u8> for AdcRange {
    type Error = CodecError;

    /// Validates a wire code against {0,1,2,3,5,6,7,11,15} (the one codec-edge conversion).
    fn try_from(code: u8) -> Result<Self, CodecError> {
        match code {
            0 => Ok(AdcRange::Pm10_24),
            1 => Ok(AdcRange::Pm5_12),
            2 => Ok(AdcRange::Pm2_56),
            3 => Ok(AdcRange::Pm1_28),
            11 => Ok(AdcRange::Pm0_64),
            5 => Ok(AdcRange::Unipolar10_24),
            6 => Ok(AdcRange::Unipolar5_12),
            7 => Ok(AdcRange::Unipolar2_56),
            15 => Ok(AdcRange::Unipolar1_28),
            other => {
                tracing::warn!(code = other, "rejected ADC range code");
                Err(CodecError::InvalidRangeCode(other))
            }
        }
    }
}

impl From<AdcRange> for u8 {
    /// Returns the wire code of the range.
    fn from(r: AdcRange) -> u8 {
        match r {
            AdcRange::Pm10_24 => 0,
            AdcRange::Pm5_12 => 1,
            AdcRange::Pm2_56 => 2,
            AdcRange::Pm1_28 => 3,
            AdcRange::Pm0_64 => 11,
            AdcRange::Unipolar10_24 => 5,
            AdcRange::Unipolar5_12 => 6,
            AdcRange::Unipolar2_56 => 7,
            AdcRange::Unipolar1_28 => 15,
        }
    }
}

/// Host command opcode; the only place the integer codes 1..=4 exist.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Opcode {
    Start,
    Stop,
    Reset,
    Query,
}

impl TryFrom<u8> for Opcode {
    type Error = CodecError;

    /// Validates an opcode byte against 1..=4.
    fn try_from(b: u8) -> Result<Self, CodecError> {
        match b {
            1 => Ok(Opcode::Start),
            2 => Ok(Opcode::Stop),
            3 => Ok(Opcode::Reset),
            4 => Ok(Opcode::Query),
            other => Err(CodecError::UnknownOpcode(other)),
        }
    }
}

impl From<Opcode> for u8 {
    /// Returns the opcode byte.
    fn from(o: Opcode) -> u8 {
        match o {
            Opcode::Start => 1,
            Opcode::Stop => 2,
            Opcode::Reset => 3,
            Opcode::Query => 4,
        }
    }
}

/// A host-to-device command; Start carries the range of ADC channels 0..3.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Command {
    /// Opcode 1: configure ranges and begin streaming.
    Start {
        /// Range for ADC channels 0..3.
        ranges: [AdcRange; 4],
    },
    /// Opcode 2: stop streaming; the device answers with a stop-ack.
    Stop,
    /// Opcode 3: software-reset the board; it re-announces itself with a boot packet.
    Reset,
    /// Opcode 4: ask for a version packet carrying the current state.
    Query,
}

impl Command {
    /// Builds a Start command from raw wire codes, validating each one.
    pub fn start_from_codes(codes: [u8; 4]) -> Result<Self, CodecError> {
        Ok(Command::Start {
            ranges: [
                AdcRange::from_code(codes[0])?,
                AdcRange::from_code(codes[1])?,
                AdcRange::from_code(codes[2])?,
                AdcRange::from_code(codes[3])?,
            ],
        })
    }

    /// Returns the opcode byte (1..=4).
    #[must_use]
    pub fn opcode(&self) -> u8 {
        u8::from(self.kind())
    }

    fn kind(&self) -> Opcode {
        match self {
            Command::Start { .. } => Opcode::Start,
            Command::Stop => Opcode::Stop,
            Command::Reset => Opcode::Reset,
            Command::Query => Opcode::Query,
        }
    }

    /// Encodes the command as its fixed 62-byte frame.
    pub fn encode(&self) -> [u8; COMMAND_LEN] {
        let mut f = [0u8; COMMAND_LEN];
        f[0] = SYNC;
        f[1] = self.opcode();
        if let Command::Start { ranges } = self {
            for (slot, r) in f[2..6].iter_mut().zip(ranges) {
                *slot = r.code();
            }
        }
        f[COMMAND_LEN - 4..].copy_from_slice(&TAIL);
        tracing::debug!(opcode = self.opcode(), "encoded command");
        f
    }

    /// Decodes a 62-byte command frame (used by the simulator side).
    pub fn decode(frame: &[u8]) -> Result<Self, CodecError> {
        let Ok(f) = <&[u8; COMMAND_LEN]>::try_from(frame) else {
            return Err(CodecError::BadLength {
                expected: COMMAND_LEN,
                actual: frame.len(),
            });
        };
        if f[0] != SYNC {
            return Err(CodecError::BadSync(f[0]));
        }
        let tail = [f[58], f[59], f[60], f[61]];
        if tail != TAIL {
            return Err(CodecError::BadTail(tail));
        }
        match Opcode::try_from(f[1])? {
            Opcode::Start => Command::start_from_codes([f[2], f[3], f[4], f[5]]),
            Opcode::Stop => Ok(Command::Stop),
            Opcode::Reset => Ok(Command::Reset),
            Opcode::Query => Ok(Command::Query),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_invalid_codes() {
        for c in [4u8, 8, 9, 10, 12, 13, 14, 16, 255] {
            assert_eq!(AdcRange::from_code(c), Err(CodecError::InvalidRangeCode(c)));
        }
    }

    #[test]
    fn code_round_trips() {
        for r in AdcRange::ALL {
            assert_eq!(AdcRange::from_code(r.code()), Ok(r));
        }
    }

    #[test]
    fn command_round_trips() {
        let cmds = [
            Command::Stop,
            Command::Reset,
            Command::Query,
            Command::start_from_codes([0, 5, 11, 15]).unwrap(),
        ];
        for c in cmds {
            assert_eq!(Command::decode(&c.encode()), Ok(c));
        }
    }

    #[test]
    fn decode_rejects_bad_frames() {
        let good = Command::Query.encode();
        assert!(matches!(
            Command::decode(&good[..61]),
            Err(CodecError::BadLength { .. })
        ));
        let mut bad = good;
        bad[0] = 0;
        assert_eq!(Command::decode(&bad), Err(CodecError::BadSync(0)));
        let mut bad = good;
        bad[61] = 0;
        assert!(matches!(Command::decode(&bad), Err(CodecError::BadTail(_))));
        let mut bad = good;
        bad[1] = 9;
        assert_eq!(Command::decode(&bad), Err(CodecError::UnknownOpcode(9)));
    }
}

#[cfg(test)]
mod opcode_tests {
    use super::*;

    // frob:tests crates/sadi-proto/src/codec/command.rs::Command.opcode
    #[test]
    fn command_opcode_bytes() {
        assert_eq!(Command::Stop.opcode(), 2);
        assert_eq!(Command::Reset.opcode(), 3);
        assert_eq!(Command::Query.opcode(), 4);
        assert_eq!(Command::start_from_codes([0, 5, 11, 15]).unwrap().opcode(), 1);
    }
}
