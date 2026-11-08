//! Device-to-host 612-byte packets: version/boot, data and stop-ack.

use super::adc::{convert, AdcMode};
use super::command::AdcRange;
use super::{CodecError, SYNC, TAIL};

/// Length in bytes of every device packet.
pub const PACKET_LEN: usize = 612;
/// Number of samples carried by one data packet.
pub const SAMPLES_PER_PACKET: usize = 50;

const PAYLOAD_OFFSET: usize = 8;
const SAMPLE_LEN: usize = 12;

/// Device packet type byte; the only place the integer codes 2, 4 and 5 exist.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum PacketType {
    StopAck,
    Version,
    Data,
}

impl TryFrom<u8> for PacketType {
    type Error = CodecError;

    /// Validates a type byte against {2,4,5}.
    fn try_from(b: u8) -> Result<Self, CodecError> {
        match b {
            2 => Ok(PacketType::StopAck),
            4 => Ok(PacketType::Version),
            5 => Ok(PacketType::Data),
            other => {
                tracing::warn!(packet_type = other, "unknown device packet type");
                Err(CodecError::UnknownType(other))
            }
        }
    }
}

impl From<PacketType> for u8 {
    /// Returns the type byte.
    fn from(t: PacketType) -> u8 {
        match t {
            PacketType::StopAck => 2,
            PacketType::Version => 4,
            PacketType::Data => 5,
        }
    }
}

/// Device state byte (offset 2 of every packet).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DeviceState {
    /// 1: just booted.
    Booted,
    /// 2: stopped.
    Stopped,
    /// 3: streaming.
    Running,
    /// Any other value (not produced by the known firmware).
    Unknown(u8),
}

impl DeviceState {
    /// Maps a wire byte to a state; unknown values are preserved, not rejected.
    #[must_use]
    pub fn from_byte(b: u8) -> Self {
        match b {
            1 => DeviceState::Booted,
            2 => DeviceState::Stopped,
            3 => DeviceState::Running,
            other => DeviceState::Unknown(other),
        }
    }

    /// Returns the wire byte for this state.
    #[must_use]
    pub fn to_byte(self) -> u8 {
        match self {
            DeviceState::Booted => 1,
            DeviceState::Stopped => 2,
            DeviceState::Running => 3,
            DeviceState::Unknown(b) => b,
        }
    }
}

impl From<u8> for DeviceState {
    /// Total conversion: unknown bytes are preserved as `Unknown`.
    fn from(b: u8) -> Self {
        DeviceState::from_byte(b)
    }
}

impl From<DeviceState> for u8 {
    /// Returns the wire byte of the state.
    fn from(s: DeviceState) -> u8 {
        s.to_byte()
    }
}

/// ADC input channel 0..=3; the only way to index the four-wide ADC arrays by channel.
///
/// A bare integer is rejected at compile time; it must pass `TryFrom<u8>` first:
///
/// ```compile_fail,E0308
/// use sadi_proto::codec::Sample;
/// let s = Sample::default();
/// let _ = s.raw(3u8);
/// ```
///
/// ```
/// use sadi_proto::codec::{AdcChannel, Sample};
/// let ch = AdcChannel::try_from(3u8).unwrap();
/// assert_eq!(Sample::default().raw(ch), 0);
/// ```
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum AdcChannel {
    /// Channel 0.
    Ch0,
    /// Channel 1.
    Ch1,
    /// Channel 2.
    Ch2,
    /// Channel 3.
    Ch3,
}

impl AdcChannel {
    /// All four channels in wire order.
    pub const ALL: [AdcChannel; 4] = [
        AdcChannel::Ch0,
        AdcChannel::Ch1,
        AdcChannel::Ch2,
        AdcChannel::Ch3,
    ];

    /// Returns the zero-based array index of the channel.
    #[must_use]
    pub fn index(self) -> usize {
        match self {
            AdcChannel::Ch0 => 0,
            AdcChannel::Ch1 => 1,
            AdcChannel::Ch2 => 2,
            AdcChannel::Ch3 => 3,
        }
    }
}

/// An ADC channel number outside 0..=3.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
#[error("invalid ADC channel {0}")]
pub struct InvalidChannel(pub u8);

impl TryFrom<u8> for AdcChannel {
    type Error = InvalidChannel;

    /// Validates a channel number against 0..=3.
    fn try_from(b: u8) -> Result<Self, InvalidChannel> {
        AdcChannel::ALL
            .get(usize::from(b))
            .copied()
            .ok_or(InvalidChannel(b))
    }
}

/// A voltage in volts; keeps ADC output from mixing with raw codes or other floats.
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd, Default)]
pub struct Volts(pub f64);

impl Volts {
    /// Returns the value in volts.
    #[must_use]
    pub fn get(self) -> f64 {
        self.0
    }
}

/// Type 4 packet: firmware version plus current state.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct VersionPacket {
    /// Device state at send time.
    pub state: DeviceState,
    /// Major version (big-endian at bytes 8..9).
    pub major: u16,
    /// Minor version in thousandths (big-endian at bytes 10..11).
    pub minor: u16,
}

impl VersionPacket {
    /// Returns the version as the DLL does: major + minor / 1000.
    #[must_use]
    pub fn fw_version(&self) -> f64 {
        f64::from(self.major) + f64::from(self.minor) / 1000.0
    }
}

/// Type 2 packet: acknowledgement of a Stop command.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct StopAckPacket {
    /// Device state at send time (normally Stopped).
    pub state: DeviceState,
}

/// One 20 us acquisition tick: encoder count plus four raw ADC words.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct Sample {
    /// Quadrature encoder position (int32, little-endian on the wire).
    pub encoder: i32,
    /// Raw ADS8688 words for channels 0..3 (big-endian on the wire).
    pub adc_raw: [u16; 4],
}

impl Sample {
    /// Returns the raw ADC word of one channel.
    #[must_use]
    pub fn raw(&self, ch: AdcChannel) -> u16 {
        self.adc_raw[ch.index()]
    }

    /// Converts one channel to typed volts using that channel's Start-time range.
    #[must_use]
    pub fn volt(&self, ch: AdcChannel, ranges: &[AdcRange; 4], mode: AdcMode) -> Volts {
        Volts(convert(ranges[ch.index()], self.raw(ch), mode))
    }

    /// Converts the four raw ADC words to volts using the Start-time `ranges`.
    #[must_use]
    pub fn volts(&self, ranges: &[AdcRange; 4], mode: AdcMode) -> [f64; 4] {
        let mut out = [0.0; 4];
        for ((o, r), raw) in out.iter_mut().zip(ranges).zip(self.adc_raw) {
            *o = convert(*r, raw, mode);
        }
        out
    }
}

/// Type 5 packet: 50 samples streamed in Run state.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DataPacket {
    /// Device state at send time (normally Running).
    pub state: DeviceState,
    /// PORTD input byte.
    pub digital_inputs: u8,
    /// Per-packet counter, zeroed by Start (little-endian at bytes 4..7).
    pub msg_count: u32,
    /// The 50 samples in time order.
    pub samples: [Sample; SAMPLES_PER_PACKET],
}

/// Any decoded device packet.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Packet {
    /// Boot or Query reply.
    Version(VersionPacket),
    /// Streamed data.
    Data(Box<DataPacket>),
    /// Stop acknowledgement.
    StopAck(StopAckPacket),
}

impl Packet {
    /// Returns the device state carried by the packet.
    #[must_use]
    pub fn state(&self) -> DeviceState {
        match self {
            Packet::Version(p) => p.state,
            Packet::Data(p) => p.state,
            Packet::StopAck(p) => p.state,
        }
    }

    /// Parses exactly one 612-byte frame, validating sync, tail and type.
    pub fn parse(frame: &[u8]) -> Result<Self, CodecError> {
        let Ok(f) = <&[u8; PACKET_LEN]>::try_from(frame) else {
            return Err(CodecError::BadLength {
                expected: PACKET_LEN,
                actual: frame.len(),
            });
        };
        if f[0] != SYNC {
            return Err(CodecError::BadSync(f[0]));
        }
        let tail = [f[608], f[609], f[610], f[611]];
        if tail != TAIL {
            return Err(CodecError::BadTail(tail));
        }
        let state = DeviceState::from_byte(f[2]);
        match PacketType::try_from(f[1])? {
            PacketType::Version => Ok(Packet::Version(VersionPacket {
                state,
                major: u16::from_be_bytes([f[8], f[9]]),
                minor: u16::from_be_bytes([f[10], f[11]]),
            })),
            PacketType::StopAck => Ok(Packet::StopAck(StopAckPacket { state })),
            PacketType::Data => {
                let mut samples = [Sample::default(); SAMPLES_PER_PACKET];
                for (k, s) in samples.iter_mut().enumerate() {
                    let o = PAYLOAD_OFFSET + SAMPLE_LEN * k;
                    s.encoder = i32::from_le_bytes([f[o], f[o + 1], f[o + 2], f[o + 3]]);
                    for (c, w) in s.adc_raw.iter_mut().enumerate() {
                        let a = o + 4 + 2 * c;
                        *w = u16::from_be_bytes([f[a], f[a + 1]]);
                    }
                }
                Ok(Packet::Data(Box::new(DataPacket {
                    state,
                    digital_inputs: f[3],
                    msg_count: u32::from_le_bytes([f[4], f[5], f[6], f[7]]),
                    samples,
                })))
            }
        }
    }

    /// Encodes the packet as a 612-byte frame (used by the simulator side).
    #[must_use]
    pub fn encode(&self) -> [u8; PACKET_LEN] {
        let mut f = [0u8; PACKET_LEN];
        f[0] = SYNC;
        f[2] = self.state().to_byte();
        match self {
            Packet::Version(p) => {
                f[1] = PacketType::Version.into();
                f[8..10].copy_from_slice(&p.major.to_be_bytes());
                f[10..12].copy_from_slice(&p.minor.to_be_bytes());
            }
            Packet::StopAck(_) => f[1] = PacketType::StopAck.into(),
            Packet::Data(p) => {
                f[1] = PacketType::Data.into();
                f[3] = p.digital_inputs;
                f[4..8].copy_from_slice(&p.msg_count.to_le_bytes());
                for (k, s) in p.samples.iter().enumerate() {
                    let o = PAYLOAD_OFFSET + SAMPLE_LEN * k;
                    f[o..o + 4].copy_from_slice(&s.encoder.to_le_bytes());
                    for (c, w) in s.adc_raw.iter().enumerate() {
                        let a = o + 4 + 2 * c;
                        f[a..a + 2].copy_from_slice(&w.to_be_bytes());
                    }
                }
            }
        }
        f[608..].copy_from_slice(&TAIL);
        f
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn data_round_trips() {
        let mut samples = [Sample::default(); SAMPLES_PER_PACKET];
        samples[7] = Sample {
            encoder: -70000,
            adc_raw: [1, 0xFFFF, 0x8000, 42],
        };
        let p = Packet::Data(Box::new(DataPacket {
            state: DeviceState::Running,
            digital_inputs: 0xA5,
            msg_count: 66051,
            samples,
        }));
        assert_eq!(Packet::parse(&p.encode()), Ok(p));
    }

    #[test]
    fn version_and_ack_round_trip() {
        let v = Packet::Version(VersionPacket {
            state: DeviceState::Booted,
            major: 1,
            minor: 3,
        });
        assert_eq!(Packet::parse(&v.encode()), Ok(v.clone()));
        if let Packet::Version(p) = v {
            assert!((p.fw_version() - 1.003).abs() < 1e-12);
        }
        let a = Packet::StopAck(StopAckPacket {
            state: DeviceState::Stopped,
        });
        assert_eq!(Packet::parse(&a.encode()), Ok(a));
    }

    #[test]
    fn rejects_malformed_frames() {
        let good = Packet::StopAck(StopAckPacket {
            state: DeviceState::Stopped,
        })
        .encode();
        assert!(matches!(
            Packet::parse(&good[..611]),
            Err(CodecError::BadLength { .. })
        ));
        let mut b = good;
        b[0] = 1;
        assert_eq!(Packet::parse(&b), Err(CodecError::BadSync(1)));
        let mut b = good;
        b[611] = 0;
        assert!(matches!(Packet::parse(&b), Err(CodecError::BadTail(_))));
        let mut b = good;
        b[1] = 9;
        assert_eq!(Packet::parse(&b), Err(CodecError::UnknownType(9)));
    }

    #[test]
    fn channel_try_from_validates() {
        assert_eq!(AdcChannel::try_from(3), Ok(AdcChannel::Ch3));
        assert_eq!(AdcChannel::try_from(4), Err(InvalidChannel(4)));
        let s = Sample {
            encoder: 0,
            adc_raw: [1, 2, 3, 4],
        };
        assert_eq!(s.raw(AdcChannel::Ch2), 3);
        let ranges = [AdcRange::Pm5_12; 4];
        let v = s.volt(AdcChannel::Ch1, &ranges, AdcMode::Ideal);
        assert_eq!(v.get(), convert(AdcRange::Pm5_12, 2, AdcMode::Ideal));
    }

    #[test]
    fn unknown_state_is_preserved() {
        assert_eq!(DeviceState::from_byte(9), DeviceState::Unknown(9));
        assert_eq!(DeviceState::Unknown(9).to_byte(), 9);
    }
}
