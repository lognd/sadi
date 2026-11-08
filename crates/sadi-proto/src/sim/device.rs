//! Protocol-faithful SADI v1.003 simulator exposed as a [`Transport`].
//!
//! `SimDevice` decodes real 62-byte command frames, replies with real
//! 612-byte packets built by the codec, and derives every sample from a
//! [`SignalSource`]. Samples are a pure function of the stream-relative
//! sample index, so a run is reproducible bit-for-bit. Time is virtual by
//! default: reads advance the clock, nothing sleeps.
#![deny(clippy::wildcard_enum_match_arm)]
// frob:ticket 01M6W7R1D3BVJZMCDT7CSWAMV8

use std::collections::VecDeque;
use std::num::NonZeroU32;
use std::time::{Duration, Instant};

use tracing::{debug, info, trace, warn};

use crate::codec::{
    AdcMode, AdcRange, CodecError, Command, DataPacket, DeviceState, Packet, Sample, StopAckPacket,
    VersionPacket, COMMAND_LEN, SAMPLES_PER_PACKET, SYNC,
};
use crate::error::TransportError;
use crate::sim::scenario::{Scenario, ScenarioError};
use crate::sim::signal::SignalSource;
use crate::transport::Transport;

/// Firmware sample rate in hertz (TCD1 period, protocol.md section 3.3).
pub const DEFAULT_SAMPLE_RATE_HZ: u32 = 50_000;
/// Most undelivered data packets kept; older ones are dropped like a full FIFO.
pub const MAX_BACKLOG_PACKETS: u64 = 1024;

const FW_MAJOR: u16 = 1;
const FW_MINOR: u16 = 3;
const NANOS_PER_SEC: u128 = 1_000_000_000;

/// Failures raised while constructing a [`SimDevice`].
#[derive(Debug, thiserror::Error)]
pub enum SimError {
    /// A sample rate of zero hertz was requested.
    #[error("sample rate must be non-zero")]
    ZeroSampleRate,
    /// The named scenario could not be built.
    #[error("scenario error: {0}")]
    Scenario(#[from] ScenarioError),
}

/// Validated ADC sample rate in hertz (non-zero).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SampleRate(NonZeroU32);

impl SampleRate {
    /// Validates `hz`; zero is rejected.
    pub fn new(hz: u32) -> Result<Self, SimError> {
        NonZeroU32::new(hz).map(SampleRate).ok_or_else(|| {
            warn!("rejected zero sample rate");
            SimError::ZeroSampleRate
        })
    }

    /// Returns the rate in hertz.
    #[must_use]
    pub fn hz(self) -> u32 {
        self.0.get()
    }
}

impl Default for SampleRate {
    /// Returns the firmware rate, 50 kHz.
    fn default() -> Self {
        SampleRate(NonZeroU32::new(DEFAULT_SAMPLE_RATE_HZ).unwrap_or(NonZeroU32::MIN))
    }
}

/// Index of a data packet since the last Start (the on-wire msgCount, widened).
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct PacketIndex(u64);

impl PacketIndex {
    /// Returns the raw index.
    #[must_use]
    pub fn get(self) -> u64 {
        self.0
    }

    /// Returns the wire msgCount (wraps at 2^32 like the firmware counter).
    #[must_use]
    pub fn msg_count(self) -> u32 {
        (self.0 & u64::from(u32::MAX)) as u32
    }
}

/// How simulated time passes.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ClockMode {
    /// Reads advance a virtual clock instantly; deterministic and fast.
    Virtual,
    /// Wall-clock pacing at the real sample rate; reads sleep (demos).
    Paced,
}

/// Construction options for a [`SimDevice`]; build with the `with_*` methods.
#[derive(Debug, Clone, Copy)]
pub struct SimConfig {
    clock: ClockMode,
    adc_mode: AdcMode,
    sample_rate: SampleRate,
    digital_inputs: u8,
}

impl Default for SimConfig {
    /// Virtual clock, ideal ADC, 50 kHz, digital inputs 0.
    fn default() -> Self {
        SimConfig {
            clock: ClockMode::Virtual,
            adc_mode: AdcMode::Ideal,
            sample_rate: SampleRate::default(),
            digital_inputs: 0,
        }
    }
}

impl SimConfig {
    /// Selects the virtual or paced clock.
    #[must_use]
    pub fn with_clock(mut self, clock: ClockMode) -> Self {
        self.clock = clock;
        self
    }

    /// Selects the raw-code formula the simulator inverts (must match the decoder side).
    #[must_use]
    pub fn with_adc_mode(mut self, mode: AdcMode) -> Self {
        self.adc_mode = mode;
        self
    }

    /// Overrides the sample rate (packet rate is rate / 50).
    #[must_use]
    pub fn with_sample_rate(mut self, rate: SampleRate) -> Self {
        self.sample_rate = rate;
        self
    }

    /// Sets the constant PORTD digital-input byte reported in data packets.
    #[must_use]
    pub fn with_digital_inputs(mut self, byte: u8) -> Self {
        self.digital_inputs = byte;
        self
    }
}

/// Time source: virtual (advanced by reads) or paced against the wall clock.
#[derive(Debug)]
enum Clock {
    Virtual(Duration),
    Paced(Instant),
}

impl Clock {
    fn new(mode: ClockMode) -> Self {
        match mode {
            ClockMode::Virtual => Clock::Virtual(Duration::ZERO),
            ClockMode::Paced => Clock::Paced(Instant::now()),
        }
    }

    fn now(&self) -> Duration {
        match self {
            Clock::Virtual(t) => *t,
            Clock::Paced(origin) => origin.elapsed(),
        }
    }

    /// Moves time forward to `target`, sleeping only in paced mode.
    fn advance_to(&mut self, target: Duration) {
        match self {
            Clock::Virtual(t) => *t = (*t).max(target),
            Clock::Paced(origin) => {
                let now = origin.elapsed();
                if target > now {
                    std::thread::sleep(target - now);
                }
            }
        }
    }
}

/// Running-state data: ranges chosen at Start and the next packet to emit.
#[derive(Debug, Clone, Copy)]
struct Stream {
    ranges: [AdcRange; 4],
    origin: Duration,
    next: PacketIndex,
}

/// Firmware state machine (1 booted, 2 stopped, 3 running).
#[derive(Debug)]
enum Mode {
    Booted,
    Stopped,
    Streaming(Stream),
}

impl Mode {
    fn device_state(&self) -> DeviceState {
        match self {
            Mode::Booted => DeviceState::Booted,
            Mode::Stopped => DeviceState::Stopped,
            Mode::Streaming(_) => DeviceState::Running,
        }
    }

    fn name(&self) -> &'static str {
        match self {
            Mode::Booted => "booted",
            Mode::Stopped => "stopped",
            Mode::Streaming(_) => "streaming",
        }
    }
}

/// Inverts [`crate::codec::convert`]: the raw ADC word that decodes to `volts`.
///
/// Out-of-range and NaN inputs saturate/zero like a real converter would.
#[must_use]
pub fn raw_from_volts(range: AdcRange, volts: f64, mode: AdcMode) -> u16 {
    let v = if volts.is_nan() { 0.0 } else { volts };
    let fs = range.full_scale_volts();
    match (mode, range.is_bipolar()) {
        (AdcMode::Ideal, true) => (v / fs * 32768.0 + 32768.0).round().clamp(0.0, 65535.0) as u16,
        (AdcMode::Ideal, false) => (v / fs * 65535.0).round().clamp(0.0, 65535.0) as u16,
        (AdcMode::DllCompatible, true) => {
            let int14 = (v * 8191.0 / fs).round().clamp(-8191.0, 8191.0) as i16;
            (int14 * 4).wrapping_sub(0x7FFF) as u16
        }
        (AdcMode::DllCompatible, false) => {
            let int14 = (v * 16383.0 / fs).round().clamp(-8191.0, 8191.0) as i16;
            (int14 * 4) as u16
        }
    }
}

/// Simulated SADI board; a move-only [`Transport`] speaking v1.003.
///
/// Like the firmware it accepts every command in every state: Start while
/// running restarts the stream, Stop while stopped re-acks, Reset reboots.
pub struct SimDevice {
    source: Box<dyn SignalSource>,
    config: SimConfig,
    clock: Clock,
    mode: Mode,
    rx: Vec<u8>,
    tx: VecDeque<u8>,
    open: bool,
}

impl std::fmt::Debug for SimDevice {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SimDevice")
            .field("state", &self.mode.name())
            .field("config", &self.config)
            .field("pending_tx", &self.tx.len())
            .field("open", &self.open)
            .finish()
    }
}

impl SimDevice {
    /// Powers on a device sampling `source`; the boot packet is queued.
    #[must_use]
    pub fn new(source: Box<dyn SignalSource>, config: SimConfig) -> Self {
        let mut dev = SimDevice {
            source,
            config,
            clock: Clock::new(config.clock),
            mode: Mode::Booted,
            rx: Vec::new(),
            tx: VecDeque::new(),
            open: true,
        };
        info!(rate_hz = config.sample_rate.hz(), clock = ?config.clock, "sim device powered on");
        dev.queue_version();
        dev
    }

    /// Powers on a device driven by the built-in scenario `name`.
    pub fn with_scenario(name: &str, config: SimConfig) -> Result<Self, SimError> {
        let scenario = Scenario::builtin(name).map_err(|e| {
            warn!(scenario = name, error = %e, "unknown scenario");
            SimError::from(e)
        })?;
        info!(scenario = name, "sim device bound to scenario");
        Ok(Self::new(Box::new(scenario), config))
    }

    /// Returns the firmware state the device is currently in.
    #[must_use]
    pub fn state(&self) -> DeviceState {
        self.mode.device_state()
    }

    /// Returns the simulated time elapsed (virtual or wall).
    #[must_use]
    pub fn now(&self) -> Duration {
        self.clock.now()
    }

    fn queue_packet(&mut self, p: &Packet) {
        self.tx.extend(p.encode());
    }

    fn queue_version(&mut self) {
        let p = Packet::Version(VersionPacket {
            state: self.mode.device_state(),
            major: FW_MAJOR,
            minor: FW_MINOR,
        });
        self.queue_packet(&p);
    }

    /// Applies one decoded command to the state machine.
    fn apply(&mut self, cmd: Command) {
        let before = self.mode.name();
        match cmd {
            Command::Start { ranges } => {
                self.mode = Mode::Streaming(Stream {
                    ranges,
                    origin: self.clock.now(),
                    next: PacketIndex(0),
                });
            }
            Command::Stop => {
                self.mode = Mode::Stopped;
                let ack = Packet::StopAck(StopAckPacket {
                    state: DeviceState::Stopped,
                });
                self.queue_packet(&ack);
            }
            Command::Reset => {
                self.tx.clear();
                self.mode = Mode::Booted;
                self.queue_version();
            }
            Command::Query => self.queue_version(),
        }
        info!(
            ?cmd,
            from = before,
            to = self.mode.name(),
            "command applied"
        );
    }

    /// Frames and executes any complete commands in the receive buffer.
    fn process_rx(&mut self) {
        loop {
            let skip = self
                .rx
                .iter()
                .position(|b| *b == SYNC)
                .unwrap_or(self.rx.len());
            if skip > 0 {
                debug!(skip, "discarding non-sync command bytes");
                self.rx.drain(..skip);
            }
            if self.rx.len() < COMMAND_LEN {
                return;
            }
            match Command::decode(&self.rx[..COMMAND_LEN]) {
                Ok(cmd) => {
                    self.rx.drain(..COMMAND_LEN);
                    self.apply(cmd);
                }
                Err(CodecError::BadTail(tail)) => {
                    debug!(?tail, "bad command tail, rescanning");
                    self.rx.drain(..1);
                }
                Err(
                    e @ (CodecError::InvalidRangeCode(_)
                    | CodecError::UnknownOpcode(_)
                    | CodecError::BadLength { .. }
                    | CodecError::BadSync(_)
                    | CodecError::UnknownType(_)),
                ) => {
                    warn!(error = %e, "ignoring invalid command frame");
                    self.rx.drain(..COMMAND_LEN);
                }
            }
        }
    }

    /// Simulated time at which data packet `n` of `stream` is complete.
    fn due_time(&self, stream: &Stream, n: u64) -> Duration {
        let per_packet = u128::from(SAMPLES_PER_PACKET as u32) * NANOS_PER_SEC;
        let ns = u128::from(n + 1) * per_packet / u128::from(self.config.sample_rate.hz());
        stream.origin + Duration::new((ns / NANOS_PER_SEC) as u64, (ns % NANOS_PER_SEC) as u32)
    }

    /// Number of whole packets completed by `now` since the stream began.
    fn packets_elapsed(&self, stream: &Stream, now: Duration) -> u64 {
        let elapsed = now.saturating_sub(stream.origin).as_nanos();
        let per_packet = u128::from(SAMPLES_PER_PACKET as u32) * NANOS_PER_SEC;
        (elapsed * u128::from(self.config.sample_rate.hz()) / per_packet) as u64
    }

    fn build_data(&self, stream: &Stream, idx: PacketIndex) -> Packet {
        let rate = f64::from(self.config.sample_rate.hz());
        let mut samples = [Sample::default(); SAMPLES_PER_PACKET];
        for (k, s) in samples.iter_mut().enumerate() {
            let t = (idx.get() * SAMPLES_PER_PACKET as u64 + k as u64) as f64 / rate;
            s.encoder = self.source.encoder(t);
            for (ch, (w, range)) in s.adc_raw.iter_mut().zip(stream.ranges).enumerate() {
                *w = raw_from_volts(range, self.source.voltage(ch, t), self.config.adc_mode);
            }
        }
        Packet::Data(Box::new(DataPacket {
            state: DeviceState::Running,
            digital_inputs: self.config.digital_inputs,
            msg_count: idx.msg_count(),
            samples,
        }))
    }

    /// Queues every data packet that is due at the current time.
    fn produce_due(&mut self) {
        let Mode::Streaming(mut stream) = self.mode else {
            return;
        };
        let elapsed = self.packets_elapsed(&stream, self.clock.now());
        let due = elapsed.saturating_sub(stream.next.get());
        if due > MAX_BACKLOG_PACKETS {
            let skipped = due - MAX_BACKLOG_PACKETS;
            warn!(skipped, "reader too slow, dropping packets");
            stream.next = PacketIndex(stream.next.get() + skipped);
        }
        while stream.next.get() < elapsed {
            let p = self.build_data(&stream, stream.next);
            trace!(msg_count = stream.next.msg_count(), "data packet produced");
            self.queue_packet(&p);
            stream.next = PacketIndex(stream.next.get() + 1);
        }
        self.mode = Mode::Streaming(stream);
    }

    /// Time at which the next data packet completes, if streaming.
    fn next_due(&self) -> Option<Duration> {
        match &self.mode {
            Mode::Streaming(s) => Some(self.due_time(s, s.next.get())),
            Mode::Booted | Mode::Stopped => None,
        }
    }
}

impl Transport for SimDevice {
    /// Feeds host bytes to the firmware command parser.
    fn write_all(&mut self, data: &[u8]) -> Result<(), TransportError> {
        if !self.open {
            warn!("write on closed sim device");
            return Err(TransportError::Closed);
        }
        self.produce_due();
        self.rx.extend_from_slice(data);
        self.process_rx();
        Ok(())
    }

    /// Returns queued bytes, advancing the clock to the next packet if none wait.
    fn read(&mut self, buf: &mut [u8], timeout: Duration) -> Result<usize, TransportError> {
        if !self.open {
            warn!("read on closed sim device");
            return Err(TransportError::Closed);
        }
        if buf.is_empty() {
            return Ok(0);
        }
        self.produce_due();
        if self.tx.is_empty() {
            let deadline = self.clock.now() + timeout;
            let target = self
                .next_due()
                .filter(|t| *t <= deadline)
                .unwrap_or(deadline);
            self.clock.advance_to(target);
            self.produce_due();
            if self.tx.is_empty() {
                debug!(?timeout, "sim read timed out");
                return Err(TransportError::Timeout(timeout));
            }
        }
        let n = buf.len().min(self.tx.len());
        for (slot, b) in buf.iter_mut().zip(self.tx.drain(..n)) {
            *slot = b;
        }
        trace!(n, left = self.tx.len(), "sim read");
        Ok(n)
    }

    /// Discards unread device output and unparsed host input.
    fn purge(&mut self) -> Result<(), TransportError> {
        if !self.open {
            return Err(TransportError::Closed);
        }
        info!(tx = self.tx.len(), rx = self.rx.len(), "sim purge");
        self.tx.clear();
        self.rx.clear();
        Ok(())
    }

    /// Powers the simulated link down; later calls return `Closed`.
    fn close(&mut self) -> Result<(), TransportError> {
        if !self.open {
            return Err(TransportError::Closed);
        }
        info!("sim device closed");
        self.open = false;
        Ok(())
    }

    /// Describes the simulator and its sample rate.
    fn description(&self) -> String {
        format!("sadi-sim v1.003 ({} Hz)", self.config.sample_rate.hz())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // frob:tests crates/sadi-proto/src/sim/device.rs::raw_from_volts
    #[test]
    fn raw_from_volts_inverts_convert() {
        use crate::codec::convert;
        for mode in [AdcMode::Ideal, AdcMode::DllCompatible] {
            for r in AdcRange::ALL {
                let fs = r.full_scale_volts();
                for frac in [0.0, 0.1, 0.25, 0.4] {
                    let v = fs * frac;
                    let back = convert(r, raw_from_volts(r, v, mode), mode);
                    assert!((back - v).abs() < fs / 4000.0, "{r:?} {mode:?} {v} {back}");
                }
            }
        }
    }

    // frob:tests crates/sadi-proto/src/sim/device.rs::PacketIndex.get
    // frob:tests crates/sadi-proto/src/sim/device.rs::PacketIndex.msg_count
    #[test]
    fn packet_index_wraps_msg_count_at_32_bits() {
        let i = PacketIndex((1 << 32) + 5);
        assert_eq!(i.get(), (1 << 32) + 5);
        assert_eq!(i.msg_count(), 5);
    }

    #[test]
    fn zero_rate_rejected() {
        assert!(matches!(SampleRate::new(0), Err(SimError::ZeroSampleRate)));
    }
}
