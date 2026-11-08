//! Tests of the seeded byte-level fault wrapper (ticket ZCE4AHC).

use std::collections::VecDeque;
use std::time::Duration;

use sadi_proto::sim::byte_faults::{ByteFaultKind, ByteFaultPlan, FaultyTransport, Probability};
use sadi_proto::{Transport, TransportError};

const T: Duration = Duration::from_millis(5);

/// Inner transport serving a fixed script of bytes, then timing out.
struct Mock {
    data: VecDeque<u8>,
    written: Vec<u8>,
}

impl Mock {
    fn new(n: usize) -> Self {
        Self {
            data: (0..n).map(|i| (i % 251) as u8).collect(),
            written: Vec::new(),
        }
    }
}

impl Transport for Mock {
    fn write_all(&mut self, data: &[u8]) -> Result<(), TransportError> {
        self.written.extend_from_slice(data);
        Ok(())
    }
    fn read(&mut self, buf: &mut [u8], t: Duration) -> Result<usize, TransportError> {
        if self.data.is_empty() {
            return Err(TransportError::Timeout(t));
        }
        let n = buf.len().min(self.data.len());
        for slot in buf.iter_mut().take(n) {
            *slot = self.data.pop_front().expect("length checked");
        }
        Ok(n)
    }
    fn purge(&mut self) -> Result<(), TransportError> {
        self.data.clear();
        Ok(())
    }
    fn close(&mut self) -> Result<(), TransportError> {
        Ok(())
    }
    fn description(&self) -> String {
        "mock".into()
    }
}

fn p(v: f64) -> Probability {
    Probability::new(v).expect("valid probability")
}

fn everything(seed: u64) -> ByteFaultPlan {
    ByteFaultPlan::default()
        .with_seed(seed)
        .with_drop(p(0.1))
        .with_duplicate(p(0.1))
        .with_flip(p(0.1))
        .with_truncate(p(0.2))
        .with_stall(p(0.2))
        .with_short_read(p(0.3))
}

/// Drain the transport; each outcome is bytes read or a timeout marker.
fn drain(t: &mut FaultyTransport<Mock>) -> Vec<Result<Vec<u8>, ()>> {
    let mut out = Vec::new();
    let mut idle = 0;
    while idle < 50 {
        let mut b = [0u8; 16];
        match t.read(&mut b, T) {
            Ok(n) => {
                idle = 0;
                out.push(Ok(b[..n].to_vec()));
            }
            Err(TransportError::Timeout(_)) => {
                idle += 1;
                out.push(Err(()));
            }
            Err(e) => panic!("unexpected error {e}"),
        }
    }
    out
}

fn bytes(r: &[Result<Vec<u8>, ()>]) -> Vec<u8> {
    r.iter().flatten().flatten().copied().collect()
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::FaultyTransport.new
// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::FaultyTransport.read
#[test]
fn same_seed_reproduces_exact_fault_sequence() {
    let mut a = FaultyTransport::new(Mock::new(2000), everything(42));
    let mut b = FaultyTransport::new(Mock::new(2000), everything(42));
    let ra = drain(&mut a);
    assert_eq!(ra, drain(&mut b));
    assert_eq!(a.stats(), b.stats());
    let s = a.stats();
    assert!(s.dropped > 0 && s.duplicated > 0 && s.flipped > 0);
    assert!(s.truncated > 0 && s.stalls > 0 && s.short_reads > 0);
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::FaultyTransport.read
#[test]
fn different_seeds_diverge() {
    let mut a = FaultyTransport::new(Mock::new(2000), everything(1));
    let mut b = FaultyTransport::new(Mock::new(2000), everything(2));
    assert_ne!(bytes(&drain(&mut a)), bytes(&drain(&mut b)));
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::FaultyTransport.read
#[test]
fn zero_plan_is_transparent() {
    let mut t = FaultyTransport::new(Mock::new(500), ByteFaultPlan::default());
    let want: Vec<u8> = Mock::new(500).data.into_iter().collect();
    assert_eq!(bytes(&drain(&mut t)), want);
    assert_eq!(t.stats(), Default::default());
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::ByteFaultPlan.with_drop
#[test]
fn certain_drop_loses_everything() {
    let plan = ByteFaultPlan::default().with_drop(Probability::ALWAYS);
    let mut t = FaultyTransport::new(Mock::new(100), plan);
    assert!(bytes(&drain(&mut t)).is_empty());
    assert_eq!(t.stats().dropped, 100);
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::ByteFaultPlan.with_duplicate
#[test]
fn certain_duplicate_doubles_every_byte() {
    let plan = ByteFaultPlan::default().with_duplicate(Probability::ALWAYS);
    let mut t = FaultyTransport::new(Mock::new(100), plan);
    assert_eq!(bytes(&drain(&mut t)).len(), 200);
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::ByteFaultPlan.with_flip
#[test]
fn certain_flip_changes_exactly_one_bit_per_byte() {
    let plan = ByteFaultPlan::default().with_flip(Probability::ALWAYS);
    let mut t = FaultyTransport::new(Mock::new(100), plan);
    let got = bytes(&drain(&mut t));
    let want: Vec<u8> = Mock::new(100).data.into_iter().collect();
    assert_eq!(got.len(), want.len());
    for (g, w) in got.iter().zip(&want) {
        assert_eq!((g ^ w).count_ones(), 1);
    }
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::ByteFaultPlan.with_truncate
#[test]
fn certain_truncate_always_loses_a_tail() {
    let plan = ByteFaultPlan::default().with_truncate(Probability::ALWAYS);
    let mut t = FaultyTransport::new(Mock::new(160), plan);
    let got = bytes(&drain(&mut t));
    assert!(got.len() < 160);
    assert_eq!(got.len() as u64 + t.stats().truncated, 160);
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::ByteFaultPlan.with_stall
#[test]
fn certain_stall_never_delivers() {
    let plan = ByteFaultPlan::default().with_stall(Probability::ALWAYS);
    let mut t = FaultyTransport::new(Mock::new(10), plan);
    let mut b = [0u8; 4];
    assert!(matches!(t.read(&mut b, T), Err(TransportError::Timeout(_))));
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::ByteFaultPlan.with_short_read
#[test]
fn certain_short_read_never_fills_buffer_but_loses_nothing() {
    let plan = ByteFaultPlan::default().with_short_read(Probability::ALWAYS);
    let mut t = FaultyTransport::new(Mock::new(160), plan);
    let r = drain(&mut t);
    assert!(r.iter().flatten().all(|c| c.len() < 16));
    assert_eq!(bytes(&r).len(), 160);
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::Probability.new
// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::Probability.get
#[test]
fn probability_rejects_out_of_range_and_non_finite() {
    for bad in [-0.1, 1.1, f64::NAN, f64::INFINITY] {
        assert!(Probability::new(bad).is_err(), "{bad}");
    }
    assert!(Probability::new(0.0).is_ok() && Probability::new(1.0).is_ok());
    assert!(serde_json::from_str::<Probability>("1.5").is_err());
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::ByteFaultPlan.active_kinds
// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::ByteFaultPlan.with_seed
#[test]
fn plan_serde_roundtrip_and_active_kinds() {
    let plan: ByteFaultPlan =
        serde_json::from_str(r#"{"seed":9,"drop":0.01,"stall":0.5}"#).expect("parse");
    assert_eq!(plan.seed.0, 9);
    assert_eq!(
        plan.active_kinds(),
        vec![ByteFaultKind::Drop, ByteFaultKind::Stall]
    );
    let back: ByteFaultPlan =
        serde_json::from_str(&serde_json::to_string(&plan).expect("ser")).expect("de");
    assert_eq!(plan, back);
    assert!(serde_json::from_str::<ByteFaultPlan>(r#"{"bogus":1}"#).is_err());
    assert!(serde_json::from_str::<ByteFaultPlan>(r#"{"drop":2}"#).is_err());
}

// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::FaultyTransport.write_all
// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::FaultyTransport.description
// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::FaultyTransport.purge
// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::FaultyTransport.close
// frob:tests crates/sadi-proto/src/sim/byte_faults.rs::FaultyTransport.into_inner
#[test]
fn writes_and_control_calls_pass_through() {
    let mut t = FaultyTransport::new(Mock::new(10), everything(3));
    t.write_all(b"abc").expect("write");
    assert_eq!(t.description(), "faulty(mock)");
    t.purge().expect("purge");
    t.close().expect("close");
    assert_eq!(t.into_inner().written, b"abc");
}
