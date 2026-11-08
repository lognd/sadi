//! Typestate session over a [`Transport`]: Disconnected -> Connected -> Streaming -> Stopped.
//!
//! Each phase is a distinct move-only type; every phase change consumes the
//! handle and returns `Result<Next, TransitionError<Previous>>`, so a failed
//! transition hands the device back instead of losing it. The wire protocol is
//! UNVERIFIED until a hardware session (docs/protocol.md section 10): every
//! timing and every skip rule below is configuration, not a constant.
//!
//! Calls that make no sense in a phase do not exist in that phase, so they
//! fail to compile. The shared preamble below is hidden; the passing example
//! shows the valid order and the failing ones differ by a single line.
//!
//! ```
//! # use sadi_proto::session::*;
//! # use sadi_proto::codec::AdcRange;
//! # use sadi_proto::{Transport, TransportError};
//! # use std::time::Duration;
//! # struct Null;
//! # impl Transport for Null {
//! #     fn write_all(&mut self, _: &[u8]) -> Result<(), TransportError> { Ok(()) }
//! #     fn read(&mut self, _: &mut [u8], t: Duration) -> Result<usize, TransportError> { Err(TransportError::Timeout(t)) }
//! #     fn purge(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn close(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn description(&self) -> String { "null".into() }
//! # }
//! # fn demo(connected: Connected<Null>) {
//! let streaming = match connected.start([AdcRange::default(); 4]) {
//!     Ok(s) => s,
//!     Err(e) => { let _back: Connected<Null> = e.into_handle(); return; }
//! };
//! let _stopped = streaming.stop();
//! # }
//! ```
//!
//! Reading blocks before Start does not compile (`Connected` has no `read_block`):
//!
//! ```compile_fail,E0599
//! # use sadi_proto::session::*;
//! # use sadi_proto::{Transport, TransportError};
//! # use std::time::Duration;
//! # struct Null;
//! # impl Transport for Null {
//! #     fn write_all(&mut self, _: &[u8]) -> Result<(), TransportError> { Ok(()) }
//! #     fn read(&mut self, _: &mut [u8], t: Duration) -> Result<usize, TransportError> { Err(TransportError::Timeout(t)) }
//! #     fn purge(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn close(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn description(&self) -> String { "null".into() }
//! # }
//! # fn demo(mut connected: Connected<Null>) {
//! let _ = connected.read_block();
//! # }
//! ```
//!
//! Stopping twice does not compile (`stop` consumes the handle):
//!
//! ```compile_fail,E0382
//! # use sadi_proto::session::*;
//! # use sadi_proto::{Transport, TransportError};
//! # use std::time::Duration;
//! # struct Null;
//! # impl Transport for Null {
//! #     fn write_all(&mut self, _: &[u8]) -> Result<(), TransportError> { Ok(()) }
//! #     fn read(&mut self, _: &mut [u8], t: Duration) -> Result<usize, TransportError> { Err(TransportError::Timeout(t)) }
//! #     fn purge(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn close(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn description(&self) -> String { "null".into() }
//! # }
//! # fn demo(streaming: Streaming<Null>) {
//! let _first = streaming.stop();
//! let _second = streaming.stop();
//! # }
//! ```
//!
//! Starting a stream that is already streaming does not compile:
//!
//! ```compile_fail,E0599
//! # use sadi_proto::session::*;
//! # use sadi_proto::codec::AdcRange;
//! # use sadi_proto::{Transport, TransportError};
//! # use std::time::Duration;
//! # struct Null;
//! # impl Transport for Null {
//! #     fn write_all(&mut self, _: &[u8]) -> Result<(), TransportError> { Ok(()) }
//! #     fn read(&mut self, _: &mut [u8], t: Duration) -> Result<usize, TransportError> { Err(TransportError::Timeout(t)) }
//! #     fn purge(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn close(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn description(&self) -> String { "null".into() }
//! # }
//! # fn demo(streaming: Streaming<Null>) {
//! let _ = streaming.start([AdcRange::default(); 4]);
//! # }
//! ```
//!
//! Using the old handle after a successful transition does not compile:
//!
//! ```compile_fail,E0382
//! # use sadi_proto::session::*;
//! # use sadi_proto::{Transport, TransportError};
//! # use std::time::Duration;
//! # struct Null;
//! # impl Transport for Null {
//! #     fn write_all(&mut self, _: &[u8]) -> Result<(), TransportError> { Ok(()) }
//! #     fn read(&mut self, _: &mut [u8], t: Duration) -> Result<usize, TransportError> { Err(TransportError::Timeout(t)) }
//! #     fn purge(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn close(&mut self) -> Result<(), TransportError> { Ok(()) }
//! #     fn description(&self) -> String { "null".into() }
//! # }
//! # fn demo(disconnected: Disconnected<Null>) {
//! let _connected = disconnected.connect();
//! let _again = disconnected.connect();
//! # }
//! ```
#![forbid(unsafe_code)]
#![deny(clippy::wildcard_enum_match_arm)]

use std::collections::VecDeque;
use std::fmt;
use std::time::{Duration, Instant};

use crate::codec::{
    AdcRange, Command, DataPacket, Decoder, DecoderStats, DeviceState, Packet, Sample,
    VersionPacket,
};
use crate::error::{ProtoError, TransportError};
use crate::transport::Transport;

/// Size of the scratch buffer for one transport read.
// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
const RX_CHUNK: usize = 4096;

// ---------------------------------------------------------------------------
// Configuration newtypes
// ---------------------------------------------------------------------------

/// Invalid session configuration value.
#[derive(Debug, Clone, Copy, PartialEq, Eq, thiserror::Error)]
pub enum ConfigError {
    /// A duration that must be positive was zero.
    #[error("{0} must be greater than zero")]
    ZeroDuration(&'static str),
    /// A retry-attempt cap of zero would never send anything.
    #[error("max attempts must be greater than zero")]
    ZeroAttempts,
    /// A retry interval longer than the total timeout would never retry.
    #[error("retry interval {interval:?} exceeds timeout {timeout:?}")]
    IntervalExceedsTimeout {
        /// Requested retry interval.
        interval: Duration,
        /// Requested total timeout.
        timeout: Duration,
    },
}

macro_rules! positive_duration {
    ($(#[$meta:meta])* $name:ident, $label:literal) => {
        $(#[$meta])*
        #[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
        pub struct $name(Duration);

        impl $name {
            /// Validates a strictly positive duration.
            pub fn new(d: Duration) -> Result<Self, ConfigError> {
                if d.is_zero() {
                    tracing::warn!(field = $label, "rejected zero duration");
                    Err(ConfigError::ZeroDuration($label))
                } else {
                    Ok(Self(d))
                }
            }

            /// Validates a strictly positive duration given in milliseconds.
            pub fn from_millis(ms: u64) -> Result<Self, ConfigError> {
                Self::new(Duration::from_millis(ms))
            }

            /// Returns the wrapped duration.
            pub fn get(self) -> Duration {
                self.0
            }
        }
    };
}

positive_duration!(
    /// Time between re-sends of an unanswered command.
    RetryInterval,
    "retry interval"
);
positive_duration!(
    /// Total time one command may take before it fails with a timeout.
    CommandTimeout,
    "command timeout"
);
positive_duration!(
    /// Longest wait for a data block in [`Streaming::read_block`].
    ReadTimeout,
    "read timeout"
);

/// Cap on how many times one command is sent before giving up.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct MaxAttempts(u32);

impl MaxAttempts {
    /// Validates a non-zero attempt count.
    pub fn new(n: u32) -> Result<Self, ConfigError> {
        if n == 0 {
            tracing::warn!("rejected zero max attempts");
            Err(ConfigError::ZeroAttempts)
        } else {
            Ok(Self(n))
        }
    }

    /// Returns the cap.
    #[must_use]
    pub fn get(self) -> u32 {
        self.0
    }
}

/// Retry interval, total timeout and attempt cap for one command.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CommandPolicy {
    interval: RetryInterval,
    timeout: CommandTimeout,
    max_attempts: MaxAttempts,
}

impl CommandPolicy {
    /// Builds a policy, rejecting an interval longer than the timeout.
    pub fn new(
        interval: RetryInterval,
        timeout: CommandTimeout,
        max_attempts: MaxAttempts,
    ) -> Result<Self, ConfigError> {
        if interval.get() > timeout.get() {
            tracing::warn!(?interval, ?timeout, "interval exceeds timeout");
            return Err(ConfigError::IntervalExceedsTimeout {
                interval: interval.get(),
                timeout: timeout.get(),
            });
        }
        Ok(Self {
            interval,
            timeout,
            max_attempts,
        })
    }

    /// Builds a policy from milliseconds and seconds-as-millis with a default attempt cap.
    pub fn from_millis(interval_ms: u64, timeout_ms: u64) -> Result<Self, ConfigError> {
        Self::new(
            RetryInterval::from_millis(interval_ms)?,
            CommandTimeout::from_millis(timeout_ms)?,
            MaxAttempts::default(),
        )
    }

    /// Returns the retry interval.
    #[must_use]
    pub fn interval(&self) -> RetryInterval {
        self.interval
    }

    /// Returns the total timeout.
    #[must_use]
    pub fn timeout(&self) -> CommandTimeout {
        self.timeout
    }

    /// Returns the attempt cap.
    #[must_use]
    pub fn max_attempts(&self) -> MaxAttempts {
        self.max_attempts
    }
}

impl Default for MaxAttempts {
    /// Returns 10 000, effectively "bounded by the timeout" for the DLL defaults.
    fn default() -> Self {
        Self(10_000)
    }
}

/// The four host commands a session sends, used in errors and policy lookup.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum CommandKind {
    /// Query the version and state.
    Query,
    /// Software-reset the board and wait for its boot packet.
    Reset,
    /// Start streaming.
    Start,
    /// Stop streaming and wait for the stop acknowledgement.
    Stop,
}

impl fmt::Display for CommandKind {
    /// Writes the lowercase command name.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            CommandKind::Query => "query",
            CommandKind::Reset => "reset",
            CommandKind::Start => "start",
            CommandKind::Stop => "stop",
        })
    }
}

impl CommandKind {
    /// True if `p` is the device's answer that completes this command.
    fn accepts(self, p: &Packet) -> bool {
        match self {
            CommandKind::Query => matches!(p, Packet::Version(_)),
            CommandKind::Reset => {
                matches!(p, Packet::Version(_)) && p.state() == DeviceState::Booted
            }
            CommandKind::Start => p.state() == DeviceState::Running,
            CommandKind::Stop => matches!(p, Packet::StopAck(_)),
        }
    }
}

/// Whether Start/Stop are skipped when the device is already in the target state.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Idempotence {
    /// Mirror momLab.dll: send nothing if the last seen state already matches.
    #[default]
    SkipIfAlready,
    /// Always send the command, whatever state was last seen.
    AlwaysSend,
}

/// Which commands `connect` issues after the purge.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub enum Handshake {
    /// protocol.md section 5: Query, Reset (wait for boot packet), Query.
    #[default]
    QueryResetQuery,
    /// Query only; for boards whose boot time is unknown or unwanted.
    QueryOnly,
}

/// Session timing and behaviour switches; defaults are the momLab.dll example values (unverified).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct SessionConfig {
    query: CommandPolicy,
    reset: CommandPolicy,
    start: CommandPolicy,
    stop: CommandPolicy,
    read_timeout: ReadTimeout,
    idempotence: Idempotence,
    handshake: Handshake,
}

impl Default for SessionConfig {
    /// Query/Reset 200 ms retry, 2 s; Start 20 ms, 1 s; Stop 2 ms, 1 s (protocol.md 2.1, 5).
    fn default() -> Self {
        let p = |i, t| CommandPolicy {
            interval: RetryInterval(Duration::from_millis(i)),
            timeout: CommandTimeout(Duration::from_millis(t)),
            max_attempts: MaxAttempts::default(),
        };
        Self {
            query: p(200, 2000),
            reset: p(200, 2000),
            start: p(20, 1000),
            stop: p(2, 1000),
            read_timeout: ReadTimeout(Duration::from_millis(500)),
            idempotence: Idempotence::default(),
            handshake: Handshake::default(),
        }
    }
}

impl SessionConfig {
    /// Returns the policy for `kind`.
    #[must_use]
    pub fn policy(&self, kind: CommandKind) -> CommandPolicy {
        match kind {
            CommandKind::Query => self.query,
            CommandKind::Reset => self.reset,
            CommandKind::Start => self.start,
            CommandKind::Stop => self.stop,
        }
    }

    /// Returns a copy with the policy for `kind` replaced.
    #[must_use]
    pub fn with_policy(mut self, kind: CommandKind, policy: CommandPolicy) -> Self {
        match kind {
            CommandKind::Query => self.query = policy,
            CommandKind::Reset => self.reset = policy,
            CommandKind::Start => self.start = policy,
            CommandKind::Stop => self.stop = policy,
        }
        self
    }

    /// Returns a copy with the same policy applied to all four commands.
    #[must_use]
    pub fn with_all_policies(self, policy: CommandPolicy) -> Self {
        [
            CommandKind::Query,
            CommandKind::Reset,
            CommandKind::Start,
            CommandKind::Stop,
        ]
        .into_iter()
        .fold(self, |c, k| c.with_policy(k, policy))
    }

    /// Returns a copy with a different data-block read timeout.
    #[must_use]
    pub fn with_read_timeout(mut self, t: ReadTimeout) -> Self {
        self.read_timeout = t;
        self
    }

    /// Returns a copy with a different Start/Stop skip rule.
    #[must_use]
    pub fn with_idempotence(mut self, i: Idempotence) -> Self {
        self.idempotence = i;
        self
    }

    /// Returns a copy with a different connect handshake.
    #[must_use]
    pub fn with_handshake(mut self, h: Handshake) -> Self {
        self.handshake = h;
        self
    }

    /// Returns the data-block read timeout.
    #[must_use]
    pub fn read_timeout(&self) -> ReadTimeout {
        self.read_timeout
    }

    /// Returns the Start/Stop skip rule.
    #[must_use]
    pub fn idempotence(&self) -> Idempotence {
        self.idempotence
    }

    /// Returns the connect handshake.
    #[must_use]
    pub fn handshake(&self) -> Handshake {
        self.handshake
    }
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/// Failure reported by a [`RawTap`] (for example a WAL write error).
#[derive(Debug, thiserror::Error)]
#[error("{0}")]
pub struct TapError(String);

impl TapError {
    /// Wraps a message describing why the tap could not record the bytes.
    pub fn new(msg: impl Into<String>) -> Self {
        Self(msg.into())
    }
}

/// Failures of session operations.
#[derive(Debug, thiserror::Error)]
pub enum SessionError {
    /// The transport failed.
    #[error("transport error: {0}")]
    Transport(#[from] TransportError),
    /// A command was not answered within its policy.
    #[error("{command} timed out after {elapsed:?} ({attempts} attempts)")]
    CommandTimeout {
        /// Which command timed out.
        command: CommandKind,
        /// How many times it was sent.
        attempts: u32,
        /// Time spent waiting.
        elapsed: Duration,
    },
    /// No data packet arrived within the read timeout.
    #[error("no data block within {0:?}")]
    ReadTimeout(Duration),
    /// The device reported a state other than the one this phase requires.
    #[error("device state {actual:?}, expected {expected:?}")]
    UnexpectedState {
        /// State the phase requires.
        expected: DeviceState,
        /// State the device reported.
        actual: DeviceState,
    },
    /// The raw-byte tap refused the bytes; acquisition must stop (data-safety I9).
    #[error("raw tap failed: {0}")]
    Tap(#[from] TapError),
}

impl From<SessionError> for ProtoError {
    /// Maps transport failures through and the rest to `Unexpected`.
    fn from(e: SessionError) -> Self {
        match e {
            SessionError::Transport(t) => ProtoError::Transport(t),
            SessionError::CommandTimeout { .. }
            | SessionError::ReadTimeout(_)
            | SessionError::UnexpectedState { .. }
            | SessionError::Tap(_) => ProtoError::Unexpected(e.to_string()),
        }
    }
}

/// A failed phase change: the error plus the untouched previous-phase handle.
#[must_use]
pub struct TransitionError<H> {
    error: SessionError,
    handle: H,
}

impl<H> TransitionError<H> {
    fn new(error: SessionError, handle: H) -> Self {
        Self { error, handle }
    }

    /// Returns the underlying failure.
    pub fn error(&self) -> &SessionError {
        &self.error
    }

    /// Gives the previous-phase handle back, dropping the error.
    pub fn into_handle(self) -> H {
        self.handle
    }

    /// Splits into the failure and the previous-phase handle.
    pub fn into_parts(self) -> (SessionError, H) {
        (self.error, self.handle)
    }
}

impl<H> fmt::Debug for TransitionError<H> {
    /// Prints the error only; handles hold a transport that need not be Debug.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("TransitionError")
            .field("error", &self.error)
            .finish_non_exhaustive()
    }
}

impl<H> fmt::Display for TransitionError<H> {
    /// Writes the underlying failure.
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "session transition failed: {}", self.error)
    }
}

impl<H> std::error::Error for TransitionError<H> {
    /// Returns the underlying failure.
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        Some(&self.error)
    }
}

// ---------------------------------------------------------------------------
// Raw tap and blocks
// ---------------------------------------------------------------------------

/// Receives every raw RX byte exactly as read, before decoding (for the WAL, data-safety I6).
pub trait RawTap: Send {
    /// Records `bytes`; an error stops the session operation that read them.
    fn on_rx(&mut self, bytes: &[u8]) -> Result<(), TapError>;
}

impl<F> RawTap for F
where
    F: FnMut(&[u8]) -> Result<(), TapError> + Send,
{
    /// Calls the closure with the bytes.
    fn on_rx(&mut self, bytes: &[u8]) -> Result<(), TapError> {
        self(bytes)
    }
}

/// Decoder counters accumulated since the previous block (or since connect).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct BlockStats {
    /// Bytes dropped while resyncing.
    pub dropped_bytes: u64,
    /// Framed packets that failed to parse.
    pub malformed: u64,
    /// msgCount gap events.
    pub gap_events: u64,
    /// Data packets missing according to msgCount jumps.
    pub missed_packets: u64,
}

impl BlockStats {
    /// Difference between two decoder snapshots (`after` minus `before`).
    fn between(before: DecoderStats, after: DecoderStats) -> Self {
        Self {
            dropped_bytes: after.dropped_bytes.saturating_sub(before.dropped_bytes),
            malformed: after.malformed.saturating_sub(before.malformed),
            gap_events: after.gap_events.saturating_sub(before.gap_events),
            missed_packets: after.missed_packets.saturating_sub(before.missed_packets),
        }
    }
}

/// Decoded data packets from one `read_block` call plus loss statistics.
#[derive(Debug, Clone, PartialEq, Eq)]
#[must_use]
pub struct Block {
    packets: Vec<DataPacket>,
    stats: BlockStats,
    device_state: Option<DeviceState>,
}

impl Block {
    /// Returns the data packets in arrival order.
    #[must_use]
    pub fn packets(&self) -> &[DataPacket] {
        &self.packets
    }

    /// Consumes the block, returning its packets.
    #[must_use]
    pub fn into_packets(self) -> Vec<DataPacket> {
        self.packets
    }

    /// Iterates over every sample of every packet in time order.
    pub fn samples(&self) -> impl Iterator<Item = &Sample> {
        self.packets.iter().flat_map(|p| p.samples.iter())
    }

    /// Returns what the decoder dropped or found missing while reading this block.
    #[must_use]
    pub fn stats(&self) -> BlockStats {
        self.stats
    }

    /// Returns the device state byte last seen (mirrors packet byte 2).
    #[must_use]
    pub fn device_state(&self) -> Option<DeviceState> {
        self.device_state
    }
}

// ---------------------------------------------------------------------------
// Shared core
// ---------------------------------------------------------------------------

/// State shared by every phase; moved, never cloned, between phase types.
struct Core<T: Transport> {
    transport: T,
    decoder: Decoder,
    config: SessionConfig,
    tap: Option<Box<dyn RawTap>>,
    device_state: Option<DeviceState>,
    version: Option<VersionPacket>,
    pending: VecDeque<DataPacket>,
    /// Decoder counters already reported in a previous block.
    reported: DecoderStats,
    buf: Box<[u8; RX_CHUNK]>,
}

impl<T: Transport> Core<T> {
    fn new(transport: T, config: SessionConfig) -> Self {
        Self {
            transport,
            decoder: Decoder::new(),
            config,
            tap: None,
            device_state: None,
            version: None,
            pending: VecDeque::new(),
            reported: DecoderStats::default(),
            buf: Box::new([0u8; RX_CHUNK]),
        }
    }

    /// One transport read, tap, decode; returns the packets that completed.
    fn pump(&mut self, wait: Duration) -> Result<Vec<Packet>, SessionError> {
        let n = match self.transport.read(&mut self.buf[..], wait) {
            Ok(n) => n,
            Err(TransportError::Timeout(_)) => 0,
            Err(e) => {
                tracing::error!(error = %e, "transport read failed");
                return Err(e.into());
            }
        };
        if n == 0 {
            return Ok(Vec::new());
        }
        let chunk = &self.buf[..n];
        tracing::trace!(n, "rx chunk");
        let tap_result = match self.tap.as_mut() {
            Some(t) => t.on_rx(chunk),
            None => Ok(()),
        };
        // Decode even if the tap failed so nothing already read is discarded.
        self.decoder.push(chunk);
        if let Err(e) = tap_result {
            tracing::error!(error = %e, n, "raw tap rejected rx bytes");
            return Err(e.into());
        }
        let mut out = Vec::new();
        for item in self.decoder.drain() {
            match item {
                Ok(p) => {
                    self.observe(&p);
                    out.push(p);
                }
                Err(e) => tracing::warn!(error = %e, "skipping malformed packet"),
            }
        }
        Ok(out)
    }

    /// Mirrors device byte 2 and the latest version packet.
    fn observe(&mut self, p: &Packet) {
        let state = p.state();
        if self.device_state != Some(state) {
            tracing::info!(from = ?self.device_state, to = ?state, "device state changed");
        }
        self.device_state = Some(state);
        if let Packet::Version(v) = p {
            self.version = Some(*v);
        }
    }

    /// Queues a data packet for the next block.
    fn keep(&mut self, d: Box<DataPacket>) {
        self.pending.push_back(*d);
    }

    /// Sends `cmd`, re-sending per policy until `kind` is answered or the policy runs out.
    ///
    /// Data packets that arrive meanwhile are kept for the next block when
    /// `keep_data` is set (they are real samples) and discarded otherwise.
    fn exchange(
        &mut self,
        kind: CommandKind,
        cmd: Command,
        keep_data: bool,
    ) -> Result<(), SessionError> {
        let policy = self.config.policy(kind);
        let frame = cmd.encode();
        let started = Instant::now();
        let mut attempts = 0u32;
        tracing::info!(command = %kind, ?policy, "command begin");
        loop {
            if attempts >= policy.max_attempts().get()
                || started.elapsed() >= policy.timeout().get()
            {
                let err = SessionError::CommandTimeout {
                    command: kind,
                    attempts,
                    elapsed: started.elapsed(),
                };
                tracing::error!(error = %err, "command failed");
                return Err(err);
            }
            self.transport.write_all(&frame).map_err(|e| {
                tracing::error!(command = %kind, error = %e, "command write failed");
                e
            })?;
            attempts += 1;
            if attempts > 1 {
                tracing::warn!(command = %kind, attempts, "retrying command");
            } else {
                tracing::debug!(command = %kind, "command sent");
            }
            let sent = Instant::now();
            loop {
                let since_send = sent.elapsed();
                let total = started.elapsed();
                if since_send >= policy.interval().get() || total >= policy.timeout().get() {
                    break;
                }
                let wait =
                    (policy.interval().get() - since_send).min(policy.timeout().get() - total);
                let mut done = false;
                for p in self.pump(wait)? {
                    if !done && kind.accepts(&p) {
                        done = true;
                        tracing::info!(command = %kind, attempts, "command answered");
                    }
                    if let Packet::Data(d) = p {
                        if keep_data {
                            self.keep(d);
                        } else {
                            tracing::debug!("discarding data packet outside streaming");
                        }
                    }
                }
                if done {
                    return Ok(());
                }
            }
        }
    }

    /// Purge, then the configured Query/Reset/Query handshake.
    fn handshake(&mut self) -> Result<(), SessionError> {
        tracing::info!(transport = %self.transport.description(), "connect handshake begin");
        self.transport.purge()?;
        self.decoder.reset();
        self.reported = self.decoder.stats();
        self.pending.clear();
        self.device_state = None;
        self.exchange(CommandKind::Query, Command::Query, false)?;
        match self.config.handshake() {
            Handshake::QueryResetQuery => {
                self.exchange(CommandKind::Reset, Command::Reset, false)?;
                self.exchange(CommandKind::Query, Command::Query, false)?;
                let actual = self.device_state.unwrap_or(DeviceState::Unknown(0));
                if actual != DeviceState::Booted {
                    let err = SessionError::UnexpectedState {
                        expected: DeviceState::Booted,
                        actual,
                    };
                    tracing::error!(error = %err, "boot not confirmed");
                    return Err(err);
                }
            }
            Handshake::QueryOnly => tracing::info!("handshake: reset skipped by configuration"),
        }
        tracing::info!(state = ?self.device_state, "connect handshake done");
        Ok(())
    }

    /// Re-reads version and state with one Query.
    fn query(&mut self) -> Result<VersionPacket, SessionError> {
        self.exchange(CommandKind::Query, Command::Query, false)?;
        self.version.ok_or(SessionError::UnexpectedState {
            expected: DeviceState::Stopped,
            actual: DeviceState::Unknown(0),
        })
    }

    /// Reset and wait for the boot packet.
    fn reset(&mut self) -> Result<VersionPacket, SessionError> {
        self.exchange(CommandKind::Reset, Command::Reset, false)?;
        self.version.ok_or(SessionError::UnexpectedState {
            expected: DeviceState::Booted,
            actual: DeviceState::Unknown(0),
        })
    }

    fn skip_allowed(&self, target: DeviceState) -> bool {
        self.config.idempotence() == Idempotence::SkipIfAlready && self.device_state == Some(target)
    }
}

macro_rules! phase_accessors {
    ($ty:ident) => {
        impl<T: Transport> $ty<T> {
            /// Returns the device state byte last seen (None before any packet).
            pub fn device_state(&self) -> Option<DeviceState> {
                self.core.device_state
            }

            /// Returns the most recent version packet, if one was received.
            pub fn version(&self) -> Option<VersionPacket> {
                self.core.version
            }

            /// Returns the decoder's running loss counters.
            pub fn decoder_stats(&self) -> DecoderStats {
                self.core.decoder.stats()
            }

            /// Returns the transport description (port name, simulator, replay file).
            pub fn description(&self) -> String {
                self.core.transport.description()
            }

            /// Returns the session configuration.
            pub fn config(&self) -> &SessionConfig {
                &self.core.config
            }
        }

        impl<T: Transport> fmt::Debug for $ty<T> {
            /// Prints phase, transport description and mirrored state.
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                f.debug_struct(stringify!($ty))
                    .field("transport", &self.core.transport.description())
                    .field("device_state", &self.core.device_state)
                    .finish_non_exhaustive()
            }
        }
    };
}

// ---------------------------------------------------------------------------
// Phases
// ---------------------------------------------------------------------------

/// Convenience name for the first phase of a session.
pub type Session<T> = Disconnected<T>;

/// Phase 1: an open transport nothing has been sent on yet.
#[must_use = "a session does nothing until connected"]
pub struct Disconnected<T: Transport> {
    core: Box<Core<T>>,
}

/// Phase 2: handshake done, device stopped or booted, commands allowed, no stream.
#[must_use = "dropping a connected session leaves the device in its current state"]
pub struct Connected<T: Transport> {
    core: Box<Core<T>>,
}

/// Phase 3: the device is streaming; the only way out is `stop`.
#[must_use = "dropping a streaming session leaves the device streaming"]
pub struct Streaming<T: Transport> {
    core: Box<Core<T>>,
    ranges: [AdcRange; 4],
}

/// Phase 4: the device acknowledged Stop; trailing data is available.
#[must_use = "trailing packets are lost if the stopped session is dropped unread"]
pub struct Stopped<T: Transport> {
    core: Box<Core<T>>,
}

phase_accessors!(Disconnected);
phase_accessors!(Connected);
phase_accessors!(Streaming);
phase_accessors!(Stopped);

impl<T: Transport> Disconnected<T> {
    /// Wraps an open transport; nothing is sent until `connect`.
    pub fn new(transport: T, config: SessionConfig) -> Self {
        tracing::info!(transport = %transport.description(), "session created");
        Self {
            core: Box::new(Core::new(transport, config)),
        }
    }

    /// Installs a tap that sees every raw RX byte before decoding.
    pub fn with_tap(mut self, tap: Box<dyn RawTap>) -> Self {
        tracing::info!("raw tap installed");
        self.core.tap = Some(tap);
        self
    }

    /// Purges and runs the handshake; on failure returns this handle unchanged in phase.
    pub fn connect(mut self) -> Result<Connected<T>, TransitionError<Disconnected<T>>> {
        match self.core.handshake() {
            Ok(()) => {
                tracing::info!("phase: Disconnected -> Connected");
                Ok(Connected { core: self.core })
            }
            Err(e) => {
                tracing::error!(error = %e, "connect failed; handle returned");
                Err(TransitionError::new(e, self))
            }
        }
    }

    /// Gives the transport back without touching the device.
    #[must_use]
    pub fn into_transport(self) -> T {
        self.core.transport
    }
}

impl<T: Transport> Connected<T> {
    /// Sends Query and returns the fresh version packet (state is mirrored too).
    pub fn query(&mut self) -> Result<VersionPacket, SessionError> {
        self.core.query()
    }

    /// Sends Reset and returns the boot packet's version once state 1 is seen.
    pub fn reset(&mut self) -> Result<VersionPacket, SessionError> {
        self.core.reset()
    }

    /// Starts streaming with `ranges`; skips the send if the device is already Running (config).
    pub fn start(
        mut self,
        ranges: [AdcRange; 4],
    ) -> Result<Streaming<T>, TransitionError<Connected<T>>> {
        if self.core.skip_allowed(DeviceState::Running) {
            tracing::info!("start skipped: device already running (idempotent)");
            return Ok(Streaming {
                core: self.core,
                ranges,
            });
        }
        match self
            .core
            .exchange(CommandKind::Start, Command::Start { ranges }, true)
        {
            Ok(()) => {
                tracing::info!("phase: Connected -> Streaming");
                Ok(Streaming {
                    core: self.core,
                    ranges,
                })
            }
            Err(e) => {
                tracing::error!(error = %e, "start failed; handle returned");
                Err(TransitionError::new(e, self))
            }
        }
    }

    /// Returns to the first phase (the next `connect` repeats the handshake).
    pub fn disconnect(self) -> Disconnected<T> {
        tracing::info!("phase: Connected -> Disconnected");
        Disconnected { core: self.core }
    }
}

impl<T: Transport> Streaming<T> {
    /// Returns the ranges sent in Start, needed to convert raw words to volts.
    #[must_use]
    pub fn ranges(&self) -> &[AdcRange; 4] {
        &self.ranges
    }

    /// Waits for at least one data packet and returns everything decoded so far.
    ///
    /// Errors leave the session usable. A non-data packet whose state is not
    /// Running (device rebooted or stopped itself) yields `UnexpectedState`
    /// after queued data is retained for the next call.
    pub fn read_block(&mut self) -> Result<Block, SessionError> {
        let timeout = self.core.config.read_timeout().get();
        let started = Instant::now();
        let mut bad_state: Option<DeviceState> = None;
        while self.core.pending.is_empty() && bad_state.is_none() {
            let elapsed = started.elapsed();
            if elapsed >= timeout {
                let err = SessionError::ReadTimeout(timeout);
                tracing::warn!(error = %err, "read_block timed out");
                return Err(err);
            }
            for p in self.core.pump(timeout - elapsed)? {
                match p {
                    Packet::Data(d) => self.core.keep(d),
                    Packet::Version(v) => {
                        tracing::debug!(state = ?v.state, "version packet while streaming");
                        if v.state != DeviceState::Running {
                            bad_state = Some(v.state);
                        }
                    }
                    Packet::StopAck(a) => {
                        tracing::warn!(state = ?a.state, "unsolicited stop ack while streaming");
                        bad_state = Some(a.state);
                    }
                }
            }
        }
        if self.core.pending.is_empty() {
            let actual = bad_state.unwrap_or(DeviceState::Unknown(0));
            let err = SessionError::UnexpectedState {
                expected: DeviceState::Running,
                actual,
            };
            tracing::error!(error = %err, "device left Running");
            return Err(err);
        }
        let packets: Vec<_> = self.core.pending.drain(..).collect();
        let now = self.core.decoder.stats();
        let stats = BlockStats::between(self.core.reported, now);
        self.core.reported = now;
        tracing::debug!(packets = packets.len(), ?stats, "block ready");
        Ok(Block {
            packets,
            stats,
            device_state: self.core.device_state,
        })
    }

    /// Sends Stop until the StopAck arrives; skips the send if the device already stopped (config).
    ///
    /// Data that arrives before the ack is kept and reachable through
    /// [`Stopped::take_trailing`]; a failure returns this handle with that data intact.
    pub fn stop(mut self) -> Result<Stopped<T>, TransitionError<Streaming<T>>> {
        if self.core.skip_allowed(DeviceState::Stopped) {
            tracing::info!("stop skipped: device already stopped (idempotent)");
            return Ok(Stopped { core: self.core });
        }
        match self.core.exchange(CommandKind::Stop, Command::Stop, true) {
            Ok(()) => {
                tracing::info!("phase: Streaming -> Stopped");
                Ok(Stopped { core: self.core })
            }
            Err(e) => {
                tracing::error!(error = %e, "stop failed; handle returned");
                Err(TransitionError::new(e, self))
            }
        }
    }
}

impl<T: Transport> Stopped<T> {
    /// Removes and returns data packets that arrived before the stop acknowledgement.
    pub fn take_trailing(&mut self) -> Vec<DataPacket> {
        let v: Vec<_> = self.core.pending.drain(..).collect();
        tracing::debug!(packets = v.len(), "took trailing packets");
        v
    }

    /// Returns to Connected without a new handshake (device state is Stopped).
    ///
    /// Buffered bytes are dropped; they were already offered to the raw tap.
    pub fn restart(mut self) -> Connected<T> {
        tracing::info!(
            discarded_packets = self.core.pending.len(),
            "phase: Stopped -> Connected"
        );
        self.core.decoder.reset();
        self.core.reported = self.core.decoder.stats();
        self.core.pending.clear();
        Connected { core: self.core }
    }

    /// Closes the transport and returns it; on failure returns this handle.
    pub fn close(mut self) -> Result<T, TransitionError<Stopped<T>>> {
        match self.core.transport.close() {
            Ok(()) => {
                tracing::info!("transport closed");
                Ok(self.core.transport)
            }
            Err(e) => {
                tracing::error!(error = %e, "transport close failed; handle returned");
                Err(TransitionError::new(e.into(), self))
            }
        }
    }

    /// Gives the transport back without closing it.
    #[must_use]
    pub fn into_transport(self) -> T {
        self.core.transport
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // frob:ticket 01M6W8KJPEKBF9PF987PKS6DHA
    // frob:tests crates/sadi-proto/src/session.rs::Block.device_state
    #[test]
    fn block_reports_last_device_state() {
        let b = Block {
            packets: Vec::new(),
            stats: BlockStats::default(),
            device_state: Some(DeviceState::Running),
        };
        assert_eq!(b.device_state(), Some(DeviceState::Running));
    }

    // frob:ticket 01M6WBJVN07FZ917KP0RGND1S4
    // frob:tests crates/sadi-proto/src/session.rs::CommandPolicy.max_attempts
    #[test]
    fn policy_reports_max_attempts() {
        let cap = MaxAttempts::new(3).unwrap();
        let p = CommandPolicy::new(
            RetryInterval::from_millis(10).unwrap(),
            CommandTimeout::from_millis(100).unwrap(),
            cap,
        )
        .unwrap();
        assert_eq!(p.max_attempts(), cap);
        assert_eq!(p.max_attempts().get(), 3);
    }

    // frob:ticket 01M6WBJVN07FZ917KP0RGND1S4
    // frob:tests crates/sadi-proto/src/session.rs::SessionConfig.read_timeout
    #[test]
    fn config_reports_read_timeout() {
        let t = ReadTimeout::from_millis(750).unwrap();
        let c = SessionConfig::default().with_read_timeout(t);
        assert_eq!(c.read_timeout(), t);
    }

    // frob:ticket 01M6WBJVN07FZ917KP0RGND1S4
    // frob:tests crates/sadi-proto/src/session.rs::SessionConfig.idempotence
    #[test]
    fn config_reports_idempotence() {
        assert_eq!(
            SessionConfig::default().idempotence(),
            Idempotence::SkipIfAlready
        );
        let c = SessionConfig::default().with_idempotence(Idempotence::AlwaysSend);
        assert_eq!(c.idempotence(), Idempotence::AlwaysSend);
    }

    // frob:ticket 01M6WBJVN07FZ917KP0RGND1S4
    // frob:tests crates/sadi-proto/src/session.rs::RawTap.on_rx
    #[test]
    fn raw_tap_closure_receives_bytes_and_propagates_errors() {
        let mut seen: Vec<u8> = Vec::new();
        {
            let mut tap = |b: &[u8]| -> Result<(), TapError> {
                seen.extend_from_slice(b);
                Ok(())
            };
            RawTap::on_rx(&mut tap, &[1, 2, 3]).unwrap();
        }
        assert_eq!(seen, vec![1, 2, 3]);

        let mut failing = |_: &[u8]| -> Result<(), TapError> { Err(TapError::new("disk full")) };
        let err = RawTap::on_rx(&mut failing, &[9]).unwrap_err();
        assert_eq!(err.to_string(), "disk full");
    }
}
