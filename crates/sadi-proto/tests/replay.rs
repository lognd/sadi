//! Capture, replay and the hwprobe CLI against the simulator (no board needed).
#![deny(clippy::wildcard_enum_match_arm)]

#[path = "../examples/hwprobe.rs"]
#[allow(clippy::wildcard_enum_match_arm, clippy::must_use_candidate)]
mod hwprobe;

use std::path::PathBuf;
use std::sync::atomic::{AtomicU32, Ordering};
use std::time::Duration;

use sadi_proto::codec::AdcRange;
use sadi_proto::replay::{CaptureSet, RecordingTransport, ReplayTransport};
use sadi_proto::session::{Handshake, Session, SessionConfig};
use sadi_proto::sim::device::{SimConfig, SimDevice};
use sadi_proto::{Transport, TransportError};

static N: AtomicU32 = AtomicU32::new(0);

/// Fresh unique scratch directory.
fn scratch() -> PathBuf {
    let d = std::env::temp_dir().join(format!(
        "hwprobe-test-{}-{}",
        std::process::id(),
        N.fetch_add(1, Ordering::SeqCst)
    ));
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn args(v: &[&str]) -> Vec<String> {
    v.iter().map(|s| (*s).to_owned()).collect()
}

fn run_probe(v: &[&str]) -> hwprobe::RunSummary {
    let mut out = Vec::new();
    hwprobe::run(&args(v), &mut out).expect("probe run")
}

fn report(s: &hwprobe::RunSummary) -> serde_json::Value {
    serde_json::from_str(&std::fs::read_to_string(&s.report).unwrap()).unwrap()
}

// frob:ticket 01M6W7R20Q20BHCEP78X42K86Y
// frob:tests crates/sadi-proto/src/replay.rs::ReplayTransport
#[test]
fn replay_chunks_then_closes() {
    let mut r = ReplayTransport::from_bytes("t", (0..=99u8).collect()).with_chunk(40);
    let mut buf = [0u8; 64];
    assert_eq!(r.read(&mut buf, Duration::from_millis(10)).unwrap(), 40);
    assert_eq!(r.read(&mut buf, Duration::from_millis(10)).unwrap(), 40);
    assert_eq!(r.read(&mut buf, Duration::from_millis(10)).unwrap(), 20);
    assert!(matches!(
        r.read(&mut buf, Duration::from_millis(10)),
        Err(TransportError::Closed)
    ));
    r.write_all(&[1, 2, 3]).unwrap();
    assert_eq!(r.bytes_written(), 3);
}

// frob:ticket 01M6W7R20Q20BHCEP78X42K86Y
// frob:tests crates/sadi-proto/src/replay.rs::CaptureSet
#[test]
fn capture_names_never_collide() {
    let d = scratch();
    let a = CaptureSet::create_new(&d, "x").unwrap();
    let b = CaptureSet::create_new(&d, "x").unwrap();
    assert_ne!(a.rx_path(), b.rx_path());
    assert_ne!(a.tx_path(), b.tx_path());
    assert!(a.rx_path().exists() && b.rx_path().exists());
}

// frob:ticket 01M6W7R20Q20BHCEP78X42K86Y
// frob:tests crates/sadi-proto/src/replay.rs::RecordingTransport
#[test]
fn record_then_replay_roundtrips_through_session() {
    let d = scratch();
    let caps = CaptureSet::create_new(&d, "rt").unwrap();
    let rx = caps.rx_path().to_path_buf();
    let dev = SimDevice::with_scenario("clean", SimConfig::default()).unwrap();
    let cfg = SessionConfig::default().with_handshake(Handshake::QueryOnly);
    let conn = Session::new(RecordingTransport::new(dev, caps), cfg)
        .connect()
        .map_err(|e| e.into_parts().0)
        .unwrap();
    let s = conn
        .start([AdcRange::default(); 4])
        .map_err(|e| e.into_parts().0)
        .unwrap();
    let mut s = s;
    let mut live = Vec::new();
    for _ in 0..3 {
        live.push(s.read_block().unwrap().packets().to_vec());
    }
    drop(s);
    let bytes = std::fs::read(&rx).unwrap();
    assert!(bytes.len() > 612);

    // Replay the capture: the same session sees the same version + first packets.
    let rep = ReplayTransport::from_bytes("rt", bytes);
    let conn = Session::new(rep, cfg)
        .connect()
        .map_err(|e| e.into_parts().0)
        .unwrap();
    let mut s = conn
        .start([AdcRange::default(); 4])
        .map_err(|e| e.into_parts().0)
        .unwrap();
    let first = s.read_block().unwrap();
    assert_eq!(first.packets()[0], live[0][0]);
}

// frob:ticket 01M6W7R20Q20BHCEP78X42K86Y
// frob:tests crates/sadi-proto/examples/hwprobe.rs::run
#[test]
fn every_subcommand_runs_against_sim_and_writes_report_and_capture() {
    let d = scratch();
    let out = d.to_str().unwrap();
    let cases: [&[&str]; 6] = [
        &["query", "--count", "3"],
        &["reset-boot-time", "--count", "3", "--allow-reset"],
        &["stream-60s-with-gap-stats", "--duration-secs", "0.2"],
        &["range-sweep", "--packets", "4"],
        &["encoder-spin", "--duration-secs", "0.2"],
        &["digital-in", "--duration-secs", "0.2"],
    ];
    for c in cases {
        let mut v = c.to_vec();
        v.extend(["--sim", "clean", "--out", out]);
        let s = run_probe(&v);
        assert!(s.ok, "{c:?} failed");
        let r = report(&s);
        assert_eq!(r["status"], "ok", "{c:?}");
        assert_eq!(r["subcommand"], c[0]);
        assert!(s.capture_rx.exists());
        assert!(
            r["rx_bytes"].as_u64().unwrap() > 0,
            "{c:?} captured nothing"
        );
    }
}

// frob:ticket 01M6W7R20Q20BHCEP78X42K86Y
// frob:tests crates/sadi-proto/examples/hwprobe.rs::run
#[test]
fn enumerate_runs_without_a_source() {
    let d = scratch();
    let s = run_probe(&["enumerate", "--out", d.to_str().unwrap()]);
    assert!(s.ok);
    assert!(report(&s)["data"]["ports"].is_array());
}

// frob:ticket 01M6W7R20Q20BHCEP78X42K86Y
// frob:tests crates/sadi-proto/examples/hwprobe.rs::run
#[test]
fn field_capture_replays_as_regression_test() {
    let d = scratch();
    let o = d.to_str().unwrap();
    let live = run_probe(&[
        "stream-60s-with-gap-stats",
        "--duration-secs",
        "0.2",
        "--sim",
        "clean",
        "--out",
        o,
    ]);
    let cap = live.capture_rx.to_str().unwrap().to_owned();
    let again = run_probe(&[
        "encoder-spin",
        "--duration-secs",
        "0.05",
        "--replay",
        &cap,
        "--label",
        "rep",
        "--out",
        o,
    ]);
    assert!(again.ok);
    assert_eq!(report(&again)["status"], "ok");
}

// frob:ticket 01M6W7R20Q20BHCEP78X42K86Y
// frob:tests crates/sadi-proto/examples/hwprobe.rs::run
#[test]
fn repeated_runs_never_overwrite() {
    let d = scratch();
    let o = d.to_str().unwrap();
    let a = run_probe(&["query", "--sim", "clean", "--out", o]);
    let b = run_probe(&["query", "--sim", "clean", "--out", o]);
    assert_ne!(a.report, b.report);
    assert_ne!(a.capture_rx, b.capture_rx);
}

// frob:ticket 01M6W7R20Q20BHCEP78X42K86Y
// frob:tests crates/sadi-proto/examples/hwprobe.rs::Invocation.check_gates
#[test]
fn safety_gates_and_usage_errors() {
    let d = scratch();
    let o = d.to_str().unwrap();
    let mut sink = Vec::new();
    let r = hwprobe::run(
        &args(&["reset-boot-time", "--sim", "clean", "--out", o]),
        &mut sink,
    );
    assert!(matches!(r, Err(hwprobe::ProbeError::Gate(_))));
    let r = hwprobe::run(
        &args(&[
            "range-sweep",
            "--sim",
            "clean",
            "--codes",
            "1,2",
            "--out",
            o,
        ]),
        &mut sink,
    );
    assert!(matches!(r, Err(hwprobe::ProbeError::Gate(_))));
    let r = hwprobe::run(&args(&["bogus"]), &mut sink);
    assert!(matches!(r, Err(hwprobe::ProbeError::Usage(_))));
    let r = hwprobe::run(&args(&["query"]), &mut sink);
    assert!(matches!(r, Err(hwprobe::ProbeError::Usage(_))));
    assert_eq!(
        std::fs::read_dir(&d).unwrap().count(),
        0,
        "gates must fire before any file is made"
    );
}

// frob:ticket 01M6W7R20Q20BHCEP78X42K86Y
// frob:tests crates/sadi-proto/src/replay.rs::CaptureSet.byte_counts
// frob:tests crates/sadi-proto/src/replay.rs::CaptureSet.sync
// frob:tests crates/sadi-proto/src/replay.rs::RecordingTransport.captures
// frob:tests crates/sadi-proto/src/replay.rs::RecordingTransport.finish
// frob:tests crates/sadi-proto/src/replay.rs::ReplayTransport.remaining
// frob:tests crates/sadi-proto/src/replay.rs::CaptureFile.append
// frob:tests crates/sadi-proto/src/replay.rs::CaptureFile.sync
// frob:tests crates/sadi-proto/src/replay.rs::CaptureFile.bytes
// frob:tests crates/sadi-proto/examples/hwprobe.rs::usage
#[test]
fn recording_counts_tx_and_rx_and_finishes() {
    let d = scratch();
    let caps = CaptureSet::create_new(&d, "cnt").unwrap();
    let rep = ReplayTransport::from_bytes("c", vec![9u8; 10]);
    assert_eq!(rep.remaining(), 10);
    let mut rec = RecordingTransport::new(rep, caps);
    rec.write_all(&[1, 2, 3]).unwrap();
    let mut buf = [0u8; 16];
    let n = rec.read(&mut buf, Duration::from_millis(10)).unwrap();
    assert_eq!(n, 10);
    assert_eq!(rec.captures().byte_counts(), (10, 3));
    let (inner, mut caps) = rec.finish().unwrap();
    caps.sync().unwrap();
    assert_eq!(inner.bytes_written(), 3);
    assert_eq!(std::fs::read(caps.rx_path()).unwrap(), vec![9u8; 10]);
    assert_eq!(std::fs::read(caps.tx_path()).unwrap(), vec![1, 2, 3]);
    assert!(hwprobe::usage().contains("hwprobe"));
}
