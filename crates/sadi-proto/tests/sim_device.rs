//! Wire-level tests of the protocol-faithful simulator (ticket CSWAMV8).
//!
//! Every exchange goes through the real command encoder and packet decoder.

use std::time::Duration;

use sadi_proto::codec::{
    convert, AdcMode, AdcRange, Command, Decoder, DeviceState, Packet, SAMPLES_PER_PACKET,
};
use sadi_proto::sim::device::{ClockMode, SampleRate, SimConfig, SimDevice, SimError};
use sadi_proto::sim::scenario::Scenario;
use sadi_proto::sim::signal::SignalSource;
use sadi_proto::{Transport, TransportError};

const T: Duration = Duration::from_millis(50);

/// Deterministic analytic source: a ramp per channel and a counting encoder.
struct Ramp;

impl SignalSource for Ramp {
    fn voltage(&self, ch: usize, t: f64) -> f64 {
        (ch as f64 + 1.0) * 0.5 * (t * 40.0).sin()
    }
    fn encoder(&self, t: f64) -> i32 {
        (t * 50_000.0).round() as i32 - 3
    }
}

fn dev() -> SimDevice {
    SimDevice::new(Box::new(Ramp), SimConfig::default())
}

fn send(d: &mut SimDevice, c: Command) {
    d.write_all(&c.encode()).expect("write");
}

/// Reads until `n` packets decoded or a timeout occurs.
fn pull(d: &mut SimDevice, dec: &mut Decoder, n: usize) -> Vec<Packet> {
    let mut out = Vec::new();
    let mut buf = [0u8; 2048];
    while out.len() < n {
        match d.read(&mut buf, T) {
            Ok(k) => dec.push(&buf[..k]),
            Err(TransportError::Timeout(_)) => break,
            Err(e) => panic!("{e}"),
        }
        out.extend(dec.drain().into_iter().map(|r| r.expect("valid packet")));
    }
    out
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.new
// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.state
#[test]
fn boot_packet_then_query_reports_version_and_state() {
    let mut d = dev();
    let mut dec = Decoder::new();
    let boot = pull(&mut d, &mut dec, 1);
    let Packet::Version(v) = &boot[0] else {
        panic!("{boot:?}")
    };
    assert_eq!(v.state, DeviceState::Booted);
    assert!((v.fw_version() - 1.003).abs() < 1e-12);
    send(&mut d, Command::Query);
    let q = pull(&mut d, &mut dec, 1);
    assert!(matches!(&q[0], Packet::Version(v) if v.state == DeviceState::Booted));
    assert_eq!(d.state(), DeviceState::Booted);
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.new
#[test]
fn start_stream_stop_round_trip_with_counter_continuity() {
    let mut d = dev();
    let mut dec = Decoder::new();
    pull(&mut d, &mut dec, 1);
    send(&mut d, Command::start_from_codes([1, 1, 1, 1]).unwrap());
    assert_eq!(d.state(), DeviceState::Running);
    let pkts = pull(&mut d, &mut dec, 200);
    assert_eq!(pkts.len(), 200);
    for (i, p) in pkts.iter().enumerate() {
        let Packet::Data(p) = p else { panic!("{p:?}") };
        assert_eq!(p.msg_count, i as u32);
        assert_eq!(p.state, DeviceState::Running);
    }
    // 200 packets at 1000/s is exactly 200 ms of virtual time
    assert_eq!(d.now(), Duration::from_millis(200));
    send(&mut d, Command::Stop);
    assert_eq!(d.state(), DeviceState::Stopped);
    let tail = pull(&mut d, &mut dec, 1);
    assert!(matches!(&tail[0], Packet::StopAck(a) if a.state == DeviceState::Stopped));
    assert_eq!(dec.stats().gap_events, 0);
    assert!(pull(&mut d, &mut dec, 1).is_empty());
}

// frob:tests crates/sadi-proto/src/sim/device.rs::raw_from_volts
#[test]
fn decoded_samples_match_signal_source() {
    for mode in [AdcMode::Ideal, AdcMode::DllCompatible] {
        let cfg = SimConfig::default().with_adc_mode(mode);
        let mut d = SimDevice::new(Box::new(Ramp), cfg);
        let mut dec = Decoder::new();
        let ranges = [AdcRange::Pm5_12; 4];
        pull(&mut d, &mut dec, 1);
        send(&mut d, Command::Start { ranges });
        for (n, p) in pull(&mut d, &mut dec, 5).iter().enumerate() {
            let Packet::Data(p) = p else { panic!() };
            for (k, s) in p.samples.iter().enumerate() {
                let t = (n * SAMPLES_PER_PACKET + k) as f64 / 50_000.0;
                assert_eq!(s.encoder, Ramp.encoder(t));
                for (ch, raw) in s.adc_raw.iter().enumerate() {
                    let v = convert(ranges[ch], *raw, mode);
                    assert!((v - Ramp.voltage(ch, t)).abs() < 5.12 / 4000.0, "{mode:?}");
                }
            }
        }
    }
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.new
#[test]
fn output_is_deterministic_across_runs() {
    let run = || {
        let mut d = dev();
        send(&mut d, Command::start_from_codes([1, 2, 3, 0]).unwrap());
        let mut bytes = Vec::new();
        let mut buf = [0u8; 700];
        for _ in 0..40 {
            let n = d.read(&mut buf, T).unwrap();
            bytes.extend_from_slice(&buf[..n]);
        }
        bytes
    };
    assert_eq!(run(), run());
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.with_scenario
#[test]
fn scenario_device_streams_and_unknown_scenario_errors() {
    let mut d = SimDevice::with_scenario("clean", SimConfig::default()).unwrap();
    let mut dec = Decoder::new();
    send(
        &mut d,
        Command::Start {
            ranges: [AdcRange::Pm5_12; 4],
        },
    );
    let pkts = pull(&mut d, &mut dec, 3);
    let Packet::Data(p) = &pkts[1] else {
        panic!("{pkts:?}")
    };
    let sc = Scenario::builtin("clean").unwrap();
    let v = convert(AdcRange::Pm5_12, p.samples[0].adc_raw[0], AdcMode::Ideal);
    assert!((v - sc.voltage(0, 50.0 / 50_000.0)).abs() < 5.12 / 4000.0);
    assert!(matches!(
        SimDevice::with_scenario("nope", SimConfig::default()),
        Err(SimError::Scenario(_))
    ));
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.new
#[test]
fn commands_in_every_state_follow_firmware() {
    let mut d = dev();
    let mut dec = Decoder::new();
    pull(&mut d, &mut dec, 1);
    // Stop while booted: still acked, state becomes stopped.
    send(&mut d, Command::Stop);
    assert!(matches!(pull(&mut d, &mut dec, 1)[0], Packet::StopAck(_)));
    // Stop again: acked again.
    send(&mut d, Command::Stop);
    assert!(matches!(pull(&mut d, &mut dec, 1)[0], Packet::StopAck(_)));
    // Start, read 3, Start again restarts msgCount at 0.
    let start = Command::start_from_codes([1, 1, 1, 1]).unwrap();
    send(&mut d, start);
    pull(&mut d, &mut dec, 3);
    send(&mut d, start);
    let p = pull(&mut d, &mut dec, 1);
    assert!(matches!(&p[0], Packet::Data(p) if p.msg_count == 0));
    // Query while streaming reports Running.
    send(&mut d, Command::Query);
    let q = pull(&mut d, &mut dec, 1);
    assert!(matches!(&q[0], Packet::Version(v) if v.state == DeviceState::Running));
    // Reset reboots: only a boot packet, no stale data.
    send(&mut d, Command::Reset);
    let r = pull(&mut d, &mut dec, 2);
    assert_eq!(r.len(), 1);
    assert!(matches!(&r[0], Packet::Version(v) if v.state == DeviceState::Booted));
    assert_eq!(d.state(), DeviceState::Booted);
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.new
#[test]
fn partial_and_garbage_writes_are_reassembled() {
    let mut d = dev();
    let mut dec = Decoder::new();
    pull(&mut d, &mut dec, 1);
    let frame = Command::Query.encode();
    d.write_all(&frame[..10]).unwrap();
    assert!(pull(&mut d, &mut dec, 1).is_empty());
    d.write_all(&frame[10..61]).unwrap();
    assert!(pull(&mut d, &mut dec, 1).is_empty());
    d.write_all(&frame[61..]).unwrap();
    assert_eq!(pull(&mut d, &mut dec, 1).len(), 1);
    // leading garbage, including a false sync, then a command byte by byte
    d.write_all(&[0x00, 0x55, 0x01]).unwrap();
    for b in frame {
        d.write_all(&[b]).unwrap();
    }
    assert!(!pull(&mut d, &mut dec, 1).is_empty());
    // an invalid opcode frame is ignored, the next valid one still works
    let mut bad = frame;
    bad[1] = 9;
    d.write_all(&bad).unwrap();
    assert!(pull(&mut d, &mut dec, 1).is_empty());
    d.write_all(&frame).unwrap();
    assert_eq!(pull(&mut d, &mut dec, 1).len(), 1);
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.new
#[test]
fn small_reads_split_packets_and_idle_read_times_out() {
    let mut d = dev();
    let mut dec = Decoder::new();
    let mut buf = [0u8; 100];
    let mut total = 0;
    while total < 612 {
        let n = d.read(&mut buf, T).unwrap();
        dec.push(&buf[..n]);
        total += n;
    }
    assert_eq!(dec.drain().len(), 1);
    let before = d.now();
    assert!(matches!(
        d.read(&mut buf, T),
        Err(TransportError::Timeout(_))
    ));
    assert_eq!(d.now(), before + T);
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.new
#[test]
fn close_and_purge_behave() {
    let mut d = dev();
    d.purge().unwrap();
    let mut buf = [0u8; 700];
    assert!(matches!(
        d.read(&mut buf, T),
        Err(TransportError::Timeout(_))
    ));
    assert!(d.description().contains("50000"));
    d.close().unwrap();
    assert!(matches!(d.write_all(b"x"), Err(TransportError::Closed)));
    assert!(matches!(d.read(&mut buf, T), Err(TransportError::Closed)));
    assert!(matches!(d.close(), Err(TransportError::Closed)));
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SampleRate.new
#[test]
fn custom_rate_changes_packet_pacing() {
    let cfg = SimConfig::default()
        .with_sample_rate(SampleRate::new(25_000).unwrap())
        .with_digital_inputs(0xA5)
        .with_clock(ClockMode::Virtual);
    let mut d = SimDevice::new(Box::new(Ramp), cfg);
    let mut dec = Decoder::new();
    send(
        &mut d,
        Command::Start {
            ranges: [AdcRange::Pm5_12; 4],
        },
    );
    let pkts = pull(&mut d, &mut dec, 11);
    assert!(matches!(&pkts[1], Packet::Data(p) if p.digital_inputs == 0xA5));
    assert_eq!(d.now(), Duration::from_millis(20));
}

// frob:tests crates/sadi-proto/src/sim/device.rs::SimDevice.now
#[test]
fn paced_clock_sleeps_in_real_time() {
    let cfg = SimConfig::default().with_clock(ClockMode::Paced);
    let mut d = SimDevice::new(Box::new(Ramp), cfg);
    let mut dec = Decoder::new();
    send(
        &mut d,
        Command::Start {
            ranges: [AdcRange::Pm5_12; 4],
        },
    );
    let t0 = std::time::Instant::now();
    // frob:ticket 01M708R6FQ6BWZ4006185C0R1D
    // pull() drains whole read buffers, and a coarse/slow clock (Windows)
    // can make more packets due per read, so it may return more than the
    // 11 requested. Assert a lower bound; the real-time check below still
    // proves the paced clock actually slept.
    assert!(pull(&mut d, &mut dec, 11).len() >= 11);
    assert!(t0.elapsed() >= Duration::from_millis(9));
}
