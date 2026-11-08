//! Session state machine against a scripted mock transport (no simulator).
#![deny(clippy::wildcard_enum_match_arm)]

use std::collections::VecDeque;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use sadi_proto::codec::{
    AdcRange, Command, DataPacket, DeviceState, Packet, Sample, StopAckPacket, VersionPacket,
    SAMPLES_PER_PACKET,
};
use sadi_proto::session::{
    CommandKind, CommandPolicy, CommandTimeout, ConfigError, Handshake, Idempotence, MaxAttempts,
    ReadTimeout, RetryInterval, Session, SessionConfig, SessionError, TapError,
};
use sadi_proto::{Transport, TransportError};

const TICKET: &str = "01M6W7R1BJ1PJWFD0FQSB1MWFD";

#[derive(Default)]
struct Inner {
    replies: VecDeque<Vec<u8>>,
    rx: VecDeque<u8>,
    max_chunk: Option<usize>,
    writes: Vec<Command>,
    purges: u32,
    closed: bool,
    fail_write: bool,
}

/// Scripted transport: each write pops one reply (possibly empty) into the rx queue.
#[derive(Clone, Default)]
struct Mock(Arc<Mutex<Inner>>);

impl Mock {
    fn with<R>(&self, f: impl FnOnce(&mut Inner) -> R) -> R {
        f(&mut self.0.lock().expect("mock lock"))
    }
    fn reply(&self, bytes: Vec<u8>) {
        self.with(|i| i.replies.push_back(bytes));
    }
    fn push_rx(&self, bytes: &[u8]) {
        self.with(|i| i.rx.extend(bytes.iter().copied()));
    }
    fn writes(&self) -> Vec<Command> {
        self.with(|i| i.writes.clone())
    }
}

impl Transport for Mock {
    fn write_all(&mut self, data: &[u8]) -> Result<(), TransportError> {
        self.with(|i| {
            if i.fail_write || i.closed {
                return Err(TransportError::Closed);
            }
            let cmd = Command::decode(data).expect("session wrote a valid command");
            i.writes.push(cmd);
            if let Some(r) = i.replies.pop_front() {
                i.rx.extend(r);
            }
            Ok(())
        })
    }
    fn read(&mut self, buf: &mut [u8], timeout: Duration) -> Result<usize, TransportError> {
        let n = self.with(|i| {
            let cap = i.max_chunk.unwrap_or(buf.len()).min(buf.len());
            let n = cap.min(i.rx.len());
            for slot in buf.iter_mut().take(n) {
                *slot = i.rx.pop_front().unwrap_or(0);
            }
            n
        });
        if n == 0 {
            std::thread::sleep(timeout.min(Duration::from_millis(1)));
            return Err(TransportError::Timeout(timeout));
        }
        Ok(n)
    }
    fn purge(&mut self) -> Result<(), TransportError> {
        self.with(|i| i.purges += 1);
        Ok(())
    }
    fn close(&mut self) -> Result<(), TransportError> {
        self.with(|i| i.closed = true);
        Ok(())
    }
    fn description(&self) -> String {
        "mock".into()
    }
}

fn version(state: DeviceState) -> Vec<u8> {
    Packet::Version(VersionPacket {
        state,
        major: 1,
        minor: 3,
    })
    .encode()
    .to_vec()
}
fn ack() -> Vec<u8> {
    Packet::StopAck(StopAckPacket {
        state: DeviceState::Stopped,
    })
    .encode()
    .to_vec()
}
fn data(msg: u32) -> Vec<u8> {
    let samples = [Sample {
        encoder: msg as i32,
        adc_raw: [1, 2, 3, 4],
    }; SAMPLES_PER_PACKET];
    Packet::Data(Box::new(DataPacket {
        state: DeviceState::Running,
        digital_inputs: 0,
        msg_count: msg,
        samples,
    }))
    .encode()
    .to_vec()
}

fn ms(n: u64) -> Duration {
    Duration::from_millis(n)
}

fn fast(timeout_ms: u64) -> SessionConfig {
    let p = CommandPolicy::new(
        RetryInterval::new(ms(5)).expect("interval"),
        CommandTimeout::new(ms(timeout_ms)).expect("timeout"),
        MaxAttempts::default(),
    )
    .expect("policy");
    SessionConfig::default()
        .with_all_policies(p)
        .with_read_timeout(ReadTimeout::new(ms(40)).expect("read timeout"))
}

/// Queues the three handshake replies (Stopped, Booted, Booted).
fn script_handshake(m: &Mock) {
    m.reply(version(DeviceState::Stopped));
    m.reply(version(DeviceState::Booted));
    m.reply(version(DeviceState::Booted));
}

const RANGES: [AdcRange; 4] = [AdcRange::Pm5_12; 4];

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Disconnected.connect
// frob:tests crates/sadi-proto/src/session.rs::Connected.start
// frob:tests crates/sadi-proto/src/session.rs::Streaming.read_block
// frob:tests crates/sadi-proto/src/session.rs::Streaming.stop
#[test]
fn full_sequence_matches_protocol_section_5() {
    let _ = TICKET;
    let m = Mock::default();
    script_handshake(&m);
    m.reply(data(0));
    m.reply([data(1), ack()].concat());
    let s = Session::new(m.clone(), fast(200))
        .connect()
        .expect("connect");
    assert_eq!(s.device_state(), Some(DeviceState::Booted));
    assert_eq!(s.version().map(|v| v.major), Some(1));
    let mut s = s.start(RANGES).expect("start");
    let b = s.read_block().expect("block");
    assert_eq!(b.packets().len(), 1);
    assert_eq!(b.samples().count(), SAMPLES_PER_PACKET);
    assert_eq!(b.device_state(), Some(DeviceState::Running));
    let mut stopped = s.stop().expect("stop");
    assert_eq!(stopped.device_state(), Some(DeviceState::Stopped));
    assert_eq!(stopped.take_trailing().len(), 1);
    let t = stopped.close().expect("close");
    assert!(t.with(|i| i.closed));
    assert_eq!(
        m.writes(),
        vec![
            Command::Query,
            Command::Reset,
            Command::Query,
            Command::Start { ranges: RANGES },
            Command::Stop
        ]
    );
    assert_eq!(m.with(|i| i.purges), 1);
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Disconnected.connect
#[test]
fn silence_is_retried_then_answered() {
    let m = Mock::default();
    m.reply(vec![]);
    m.reply(vec![]);
    m.reply(version(DeviceState::Stopped));
    let cfg = fast(200).with_handshake(Handshake::QueryOnly);
    let _c = Session::new(m.clone(), cfg).connect().expect("connect");
    assert_eq!(m.writes(), vec![Command::Query; 3]);
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Connected.start
#[test]
fn start_timeout_returns_reusable_handle() {
    let m = Mock::default();
    script_handshake(&m);
    let c = Session::new(m.clone(), fast(30))
        .connect()
        .expect("connect");
    let err = c.start(RANGES).expect_err("no reply");
    assert!(matches!(
        err.error(),
        SessionError::CommandTimeout { command: CommandKind::Start, attempts, .. } if *attempts >= 2
    ));
    let c = err.into_handle();
    m.reply(data(0));
    let mut s = c.start(RANGES).expect("second try");
    assert_eq!(s.read_block().expect("block").packets().len(), 1);
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Streaming.stop
#[test]
fn duplicate_acks_are_harmless() {
    let m = Mock::default();
    script_handshake(&m);
    m.reply(data(0));
    m.reply([ack(), ack(), ack()].concat());
    let s = Session::new(m.clone(), fast(200))
        .connect()
        .expect("connect");
    let s = s.start(RANGES).expect("start");
    let stopped = s.stop().expect("stop");
    assert_eq!(stopped.decoder_stats().malformed, 0);
    let writes = m.writes();
    assert_eq!(writes.iter().filter(|c| **c == Command::Stop).count(), 1);
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Streaming.stop
#[test]
fn truncated_stop_ack_then_full_ack() {
    let m = Mock::default();
    script_handshake(&m);
    m.reply(data(0));
    m.reply(ack()[..300].to_vec());
    m.reply(ack());
    m.reply(ack());
    let s = Session::new(m.clone(), fast(500))
        .connect()
        .expect("connect");
    let s = s.start(RANGES).expect("start");
    let stopped = s.stop().expect("stop completes after resync");
    let stops = m.writes().iter().filter(|c| **c == Command::Stop).count();
    assert!(stops >= 2, "stop was retried, sent {stops}");
    assert!(stopped.decoder_stats().dropped_bytes > 0 || stopped.decoder_stats().malformed > 0);
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Disconnected.connect
#[test]
fn reset_ignores_stale_version_and_times_out_without_boot() {
    let m = Mock::default();
    m.reply(version(DeviceState::Stopped));
    m.reply(version(DeviceState::Stopped));
    let err = Session::new(m.clone(), fast(30))
        .connect()
        .expect_err("never boots");
    assert!(matches!(
        err.error(),
        SessionError::CommandTimeout {
            command: CommandKind::Reset,
            ..
        }
    ));
    let d = err.into_handle();
    drop(d.into_transport());
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Connected.start
#[test]
fn start_is_idempotent_when_already_running() {
    let m = Mock::default();
    m.reply(version(DeviceState::Running));
    let cfg = fast(200).with_handshake(Handshake::QueryOnly);
    let c = Session::new(m.clone(), cfg).connect().expect("connect");
    let s = c.start(RANGES).expect("start");
    assert_eq!(m.writes(), vec![Command::Query]);
    drop(s);

    let m = Mock::default();
    m.reply(version(DeviceState::Running));
    m.reply(data(0));
    let cfg = cfg.with_idempotence(Idempotence::AlwaysSend);
    let c = Session::new(m.clone(), cfg).connect().expect("connect");
    let _s = c.start(RANGES).expect("start");
    assert_eq!(
        m.writes(),
        vec![Command::Query, Command::Start { ranges: RANGES }]
    );
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Streaming.read_block
// frob:tests crates/sadi-proto/src/session.rs::Streaming.stop
#[test]
fn stop_is_idempotent_after_observed_stop() {
    let m = Mock::default();
    script_handshake(&m);
    m.reply(data(0));
    let c = Session::new(m.clone(), fast(200))
        .connect()
        .expect("connect");
    let mut s = c.start(RANGES).expect("start");
    let _ = s.read_block().expect("block");
    m.push_rx(&ack());
    let err = s.read_block().expect_err("device left Running");
    assert!(matches!(
        err,
        SessionError::UnexpectedState {
            expected: DeviceState::Running,
            actual: DeviceState::Stopped
        }
    ));
    let before = m.writes().len();
    let _ = s.stop().expect("stop skipped");
    assert_eq!(m.writes().len(), before);
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Disconnected.with_tap
// frob:tests crates/sadi-proto/src/session.rs::Streaming.read_block
#[test]
fn tap_sees_raw_bytes_including_garbage_and_failure_is_loud() {
    let m = Mock::default();
    script_handshake(&m);
    m.reply([vec![0xDE, 0xAD, 0xBE], data(0)].concat());
    let seen = Arc::new(Mutex::new(Vec::<u8>::new()));
    let sink = Arc::clone(&seen);
    let fail = Arc::new(Mutex::new(false));
    let fail2 = Arc::clone(&fail);
    let tap = move |b: &[u8]| -> Result<(), TapError> {
        sink.lock().expect("sink").extend_from_slice(b);
        if *fail2.lock().expect("fail") {
            Err(TapError::new("disk full"))
        } else {
            Ok(())
        }
    };
    let c = Session::new(m.clone(), fast(200))
        .with_tap(Box::new(tap))
        .connect()
        .expect("connect");
    let mut s = c.start(RANGES).expect("start");
    let b = s.read_block().expect("block");
    assert_eq!(b.stats().dropped_bytes, 3);
    let total = seen.lock().expect("seen").len();
    assert_eq!(total, 3 * 612 + 3 + 612);
    *fail.lock().expect("fail") = true;
    m.push_rx(&data(1));
    let err = s.read_block().expect_err("tap failed");
    assert!(matches!(err, SessionError::Tap(_)));
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Streaming.read_block
#[test]
fn gaps_are_reported_and_read_times_out() {
    let m = Mock::default();
    script_handshake(&m);
    m.reply([data(0), data(1), data(5)].concat());
    m.with(|i| i.max_chunk = Some(700));
    let c = Session::new(m.clone(), fast(200))
        .connect()
        .expect("connect");
    let mut s = c.start(RANGES).expect("start");
    let mut gaps = 0;
    let mut missed = 0;
    let mut n = 0;
    while n < 3 {
        let b = s.read_block().expect("block");
        n += b.packets().len();
        gaps += b.stats().gap_events;
        missed += b.stats().missed_packets;
    }
    assert_eq!((gaps, missed), (1, 3));
    assert!(matches!(s.read_block(), Err(SessionError::ReadTimeout(_))));
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::CommandPolicy.new
// frob:tests crates/sadi-proto/src/session.rs::MaxAttempts.new
#[test]
fn config_validation() {
    assert_eq!(
        RetryInterval::new(Duration::ZERO),
        Err(ConfigError::ZeroDuration("retry interval"))
    );
    assert_eq!(MaxAttempts::new(0), Err(ConfigError::ZeroAttempts));
    let r = CommandPolicy::new(
        RetryInterval::from_millis(10).expect("i"),
        CommandTimeout::from_millis(5).expect("t"),
        MaxAttempts::new(3).expect("n"),
    );
    assert!(matches!(r, Err(ConfigError::IntervalExceedsTimeout { .. })));
    let d = SessionConfig::default();
    assert_eq!(d.policy(CommandKind::Stop).interval().get(), ms(2));
    assert_eq!(d.policy(CommandKind::Query).timeout().get(), ms(2000));
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Connected.start
#[test]
fn transport_closed_during_start_returns_handle() {
    let m = Mock::default();
    script_handshake(&m);
    let c = Session::new(m.clone(), fast(200))
        .connect()
        .expect("connect");
    m.with(|i| i.fail_write = true);
    let err = c.start(RANGES).expect_err("closed");
    assert!(matches!(
        err.error(),
        SessionError::Transport(TransportError::Closed)
    ));
    let c = err.into_handle();
    assert_eq!(c.device_state(), Some(DeviceState::Booted));
}

// frob:ticket 01M6W7R1BJ1PJWFD0FQSB1MWFD
// frob:tests crates/sadi-proto/src/session.rs::Connected.query
// frob:tests crates/sadi-proto/src/session.rs::Connected.reset
// frob:tests crates/sadi-proto/src/session.rs::Connected.disconnect
// frob:tests crates/sadi-proto/src/session.rs::Disconnected.new
// frob:tests crates/sadi-proto/src/session.rs::Disconnected.into_transport
// frob:tests crates/sadi-proto/src/session.rs::Streaming.ranges
// frob:tests crates/sadi-proto/src/session.rs::Stopped.restart
// frob:tests crates/sadi-proto/src/session.rs::Stopped.close
// frob:tests crates/sadi-proto/src/session.rs::Stopped.into_transport
// frob:tests crates/sadi-proto/src/session.rs::Block.into_packets
// frob:tests crates/sadi-proto/src/session.rs::Block.stats
// frob:tests crates/sadi-proto/src/session.rs::TransitionError.into_parts
// frob:tests crates/sadi-proto/src/session.rs::TransitionError.error
// frob:tests crates/sadi-proto/src/session.rs::SessionConfig.handshake
#[test]
fn phase_utilities_and_restart() {
    let m = Mock::default();
    script_handshake(&m);
    m.reply(version(DeviceState::Stopped));
    m.reply(version(DeviceState::Booted));
    let cfg = fast(200);
    assert_eq!(cfg.handshake(), Handshake::QueryResetQuery);
    let mut c = Session::new(m.clone(), cfg).connect().expect("connect");
    assert_eq!(c.query().expect("query").major, 1);
    assert_eq!(c.reset().expect("reset").minor, 3);
    let d = c.disconnect();
    assert_eq!(d.description(), "mock");

    // failed connect: into_parts yields the error and the handle back
    let (e, d) = d.connect().expect_err("no replies left").into_parts();
    assert!(matches!(
        e,
        SessionError::CommandTimeout {
            command: CommandKind::Query,
            ..
        }
    ));
    drop(d.into_transport());

    let m = Mock::default();
    script_handshake(&m);
    m.reply(data(0));
    m.reply(ack());
    let c = Session::new(m.clone(), fast(200))
        .connect()
        .expect("connect");
    let mut s = c.start(RANGES).expect("start");
    assert_eq!(s.ranges(), &RANGES);
    let b = s.read_block().expect("block");
    assert_eq!(b.stats().dropped_bytes, 0);
    assert_eq!(b.into_packets().len(), 1);
    let stopped = s.stop().expect("stop");
    let c = stopped.restart();
    m.reply(data(1));
    m.reply(ack());
    let stopped = c
        .start(RANGES)
        .expect("restart start")
        .stop()
        .expect("stop again");
    assert_eq!(stopped.device_state(), Some(DeviceState::Stopped));
    drop(stopped.close().expect("close"));
}
