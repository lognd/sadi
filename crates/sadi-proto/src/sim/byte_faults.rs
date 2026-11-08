//! Seeded byte-level fault injection around any [`Transport`].
//!
//! [`FaultyTransport`] corrupts the device-to-host stream (drop, duplicate,
//! bit flip, truncate) and the read call itself (stall, short read), all
//! driven by one seeded splitmix64 stream shared with the signal faults.

use std::collections::VecDeque;
use std::time::Duration;

use serde::{Deserialize, Serialize};
use tracing::{debug, trace, warn};

use crate::error::TransportError;
use crate::sim::physics::RangeError;
use crate::sim::signal_faults::{splitmix64, unit, Seed};
use crate::transport::Transport;

/// A finite probability in `[0, 1]`; invalid values cannot be built.
#[derive(Debug, Clone, Copy, Default, PartialEq, PartialOrd, Serialize, Deserialize)]
#[serde(try_from = "f64", into = "f64")]
pub struct Probability(f64);

impl Probability {
    /// Never happens.
    pub const NEVER: Self = Self(0.0);
    /// Always happens.
    pub const ALWAYS: Self = Self(1.0);

    /// Smart constructor: accepts only finite values in `[0, 1]`.
    pub fn new(p: f64) -> Result<Self, RangeError> {
        if p.is_finite() && (0.0..=1.0).contains(&p) {
            Ok(Self(p))
        } else {
            warn!(p, "rejected probability outside [0, 1]");
            Err(RangeError {
                expected: "finite and in [0, 1]",
                got: p,
            })
        }
    }

    /// Wrapped value.
    #[must_use]
    pub fn get(self) -> f64 {
        self.0
    }
}

impl TryFrom<f64> for Probability {
    type Error = RangeError;
    fn try_from(p: f64) -> Result<Self, RangeError> {
        Self::new(p)
    }
}

impl From<Probability> for f64 {
    fn from(p: Probability) -> f64 {
        p.0
    }
}

/// The kinds of byte-level fault a [`ByteFaultPlan`] can inject.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum ByteFaultKind {
    /// An inbound byte vanishes.
    Drop,
    /// An inbound byte arrives twice.
    Duplicate,
    /// One bit of an inbound byte is inverted.
    Flip,
    /// The tail of an inbound chunk is lost.
    Truncate,
    /// A read returns a timeout although data may be pending.
    Stall,
    /// A read returns fewer bytes than are available.
    ShortRead,
}

impl ByteFaultKind {
    /// Every kind, in a stable order.
    pub const ALL: [ByteFaultKind; 6] = [
        ByteFaultKind::Drop,
        ByteFaultKind::Duplicate,
        ByteFaultKind::Flip,
        ByteFaultKind::Truncate,
        ByteFaultKind::Stall,
        ByteFaultKind::ShortRead,
    ];

    /// Whether `plan` actually injects this kind of fault.
    #[must_use]
    pub fn is_active(self, plan: &ByteFaultPlan) -> bool {
        let p = match self {
            ByteFaultKind::Drop => plan.drop,
            ByteFaultKind::Duplicate => plan.duplicate,
            ByteFaultKind::Flip => plan.flip,
            ByteFaultKind::Truncate => plan.truncate,
            ByteFaultKind::Stall => plan.stall,
            ByteFaultKind::ShortRead => plan.short_read,
        };
        p.get() > 0.0
    }
}

/// Serde-configurable byte-fault rates; `drop`, `duplicate` and `flip` are
/// per inbound byte, `truncate`, `stall` and `short_read` per read call.
#[derive(Debug, Clone, Copy, Default, PartialEq, Serialize, Deserialize)]
#[serde(default, deny_unknown_fields)]
pub struct ByteFaultPlan {
    /// Seed of the deterministic fault stream.
    pub seed: Seed,
    /// Per-byte probability the byte is dropped.
    pub drop: Probability,
    /// Per-byte probability the byte is delivered twice.
    pub duplicate: Probability,
    /// Per-byte probability one random bit is flipped.
    pub flip: Probability,
    /// Per-read probability the chunk is cut at a random point.
    pub truncate: Probability,
    /// Per-read probability the read times out without delivering data.
    pub stall: Probability,
    /// Per-read probability fewer bytes than available are returned.
    pub short_read: Probability,
}

impl ByteFaultPlan {
    /// Builder step: set the fault seed.
    #[must_use]
    pub fn with_seed(mut self, seed: u64) -> Self {
        self.seed = Seed(seed);
        self
    }

    /// Builder step: set the per-byte drop rate.
    #[must_use]
    pub fn with_drop(mut self, p: Probability) -> Self {
        self.drop = p;
        self
    }

    /// Builder step: set the per-byte duplicate rate.
    #[must_use]
    pub fn with_duplicate(mut self, p: Probability) -> Self {
        self.duplicate = p;
        self
    }

    /// Builder step: set the per-byte bit-flip rate.
    #[must_use]
    pub fn with_flip(mut self, p: Probability) -> Self {
        self.flip = p;
        self
    }

    /// Builder step: set the per-read truncate rate.
    #[must_use]
    pub fn with_truncate(mut self, p: Probability) -> Self {
        self.truncate = p;
        self
    }

    /// Builder step: set the per-read stall rate.
    #[must_use]
    pub fn with_stall(mut self, p: Probability) -> Self {
        self.stall = p;
        self
    }

    /// Builder step: set the per-read short-read rate.
    #[must_use]
    pub fn with_short_read(mut self, p: Probability) -> Self {
        self.short_read = p;
        self
    }

    /// Kinds of fault this plan actually injects.
    #[must_use]
    pub fn active_kinds(&self) -> Vec<ByteFaultKind> {
        ByteFaultKind::ALL
            .into_iter()
            .filter(|k| k.is_active(self))
            .collect()
    }
}

/// Counts of faults injected so far, for assertions and diagnostics.
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct ByteFaultStats {
    /// Bytes dropped.
    pub dropped: u64,
    /// Bytes duplicated.
    pub duplicated: u64,
    /// Bytes with a flipped bit.
    pub flipped: u64,
    /// Bytes lost to chunk truncation.
    pub truncated: u64,
    /// Reads turned into timeouts.
    pub stalls: u64,
    /// Reads cut short.
    pub short_reads: u64,
}

/// Counter-based deterministic draw stream keyed by the plan seed.
#[derive(Debug, Clone)]
struct FaultRng {
    seed: u64,
    counter: u64,
}

impl FaultRng {
    fn next_unit(&mut self) -> f64 {
        self.counter = self.counter.wrapping_add(1);
        unit(splitmix64(
            self.seed ^ self.counter.wrapping_mul(0xA24B_AED4_963E_E407),
        ))
    }

    fn hit(&mut self, p: Probability) -> bool {
        self.next_unit() < p.get()
    }

    /// Uniform index in `0..n` (`n > 0`).
    fn below(&mut self, n: usize) -> usize {
        ((self.next_unit() * n as f64) as usize).min(n - 1)
    }
}

/// Wraps any [`Transport`] and injects seeded byte-level faults on reads.
pub struct FaultyTransport<T: Transport> {
    inner: T,
    plan: ByteFaultPlan,
    rng: FaultRng,
    pending: VecDeque<u8>,
    stats: ByteFaultStats,
}

impl<T: Transport> FaultyTransport<T> {
    /// Wrap `inner`; the same plan (seed included) replays the same faults.
    #[must_use]
    pub fn new(inner: T, plan: ByteFaultPlan) -> Self {
        debug!(?plan, kinds = ?plan.active_kinds(), "byte faults armed");
        Self {
            inner,
            plan,
            rng: FaultRng {
                seed: plan.seed.0,
                counter: 0,
            },
            pending: VecDeque::new(),
            stats: ByteFaultStats::default(),
        }
    }

    /// Faults injected so far.
    #[must_use]
    pub fn stats(&self) -> ByteFaultStats {
        self.stats
    }

    /// Unwrap the inner transport, discarding undelivered bytes.
    #[must_use]
    pub fn into_inner(self) -> T {
        self.inner
    }

    /// Apply truncate and the per-byte faults to one inbound chunk.
    fn corrupt(&mut self, chunk: &[u8]) {
        let mut chunk = chunk;
        if !chunk.is_empty() && self.rng.hit(self.plan.truncate) {
            let keep = self.rng.below(chunk.len());
            let lost = (chunk.len() - keep) as u64;
            debug!(keep, lost, "chunk truncated");
            self.stats.truncated += lost;
            chunk = &chunk[..keep];
        }
        for &byte in chunk {
            if self.rng.hit(self.plan.drop) {
                trace!(byte, "byte dropped");
                self.stats.dropped += 1;
                continue;
            }
            let mut out = byte;
            if self.rng.hit(self.plan.flip) {
                let bit = self.rng.below(8);
                out ^= 1 << bit;
                trace!(byte, out, bit, "bit flipped");
                self.stats.flipped += 1;
            }
            self.pending.push_back(out);
            if self.rng.hit(self.plan.duplicate) {
                trace!(out, "byte duplicated");
                self.stats.duplicated += 1;
                self.pending.push_back(out);
            }
        }
    }
}

impl<T: Transport> Transport for FaultyTransport<T> {
    fn write_all(&mut self, data: &[u8]) -> Result<(), TransportError> {
        self.inner.write_all(data)
    }

    fn read(&mut self, buf: &mut [u8], timeout: Duration) -> Result<usize, TransportError> {
        if self.rng.hit(self.plan.stall) {
            debug!("read stalled");
            self.stats.stalls += 1;
            return Err(TransportError::Timeout(timeout));
        }
        if self.pending.is_empty() {
            let mut scratch = vec![0u8; buf.len()];
            let n = match self.inner.read(&mut scratch, timeout) {
                Ok(n) => n,
                Err(e) => {
                    debug!(error = %e, "inner read failed, passing through");
                    return Err(e);
                }
            };
            self.corrupt(&scratch[..n]);
            if self.pending.is_empty() {
                debug!(inner_bytes = n, "all inbound bytes lost, reporting timeout");
                return Err(TransportError::Timeout(timeout));
            }
        }
        let mut n = self.pending.len().min(buf.len());
        if n > 1 && self.rng.hit(self.plan.short_read) {
            n = 1 + self.rng.below(n - 1);
            debug!(n, "short read");
            self.stats.short_reads += 1;
        }
        for (slot, byte) in buf.iter_mut().zip(self.pending.drain(..n)) {
            *slot = byte;
        }
        trace!(n, "delivered bytes");
        Ok(n)
    }

    fn purge(&mut self) -> Result<(), TransportError> {
        debug!(discarded = self.pending.len(), "purge");
        self.pending.clear();
        self.inner.purge()
    }

    fn close(&mut self) -> Result<(), TransportError> {
        debug!("close");
        self.pending.clear();
        self.inner.close()
    }

    fn description(&self) -> String {
        format!("faulty({})", self.inner.description())
    }
}
