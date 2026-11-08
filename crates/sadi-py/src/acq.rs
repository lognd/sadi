//! Acquisition thread: a dedicated Rust reader feeding a bounded channel.
//!
//! The thread owns the streaming session (lifted out of the Python `Session`),
//! reads blocks, and pushes them into a bounded channel. Python pulls blocks
//! with the GIL released. A full channel never drops data: the reader counts
//! the event, logs it loudly, and keeps retrying until the consumer catches up
//! or a stop is requested (then the unsent block is counted as lost, loudly).
//! See `docs/device/acquisition-thread.md`.
// frob:ticket 01M6W7R2QFWW5VYSHCVA8Y67RG

use std::num::NonZeroUsize;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::mpsc::{sync_channel, Receiver, RecvTimeoutError, SyncSender, TrySendError};
use std::sync::{Arc, Mutex, MutexGuard, PoisonError};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use sadi_proto::session::{BlockStats, SessionError};

use crate::convert::{Block, BlockData};
use crate::errors::BindError;
use crate::session::{Session, StreamParts};

/// Default acquisition channel capacity in blocks (docs/concurrency.md).
pub const ACQ_CHANNEL_BLOCKS: usize = 256;

/// Pause between retries while the channel is full.
const FULL_RETRY: Duration = Duration::from_millis(1);

/// Time a full channel may persist before the consumer is flagged as stalled.
const STALL_AFTER: Duration = Duration::from_secs(5);

/// Failures of the acquisition machinery itself.
#[derive(Debug, thiserror::Error)]
pub enum AcqError {
    /// Channel capacity must be at least one block.
    #[error("channel capacity must be >= 1")]
    ZeroCapacity,
    /// The OS refused to start the thread.
    #[error("cannot spawn acquisition thread: {0}")]
    Spawn(#[source] std::io::Error),
    /// `join` was already called.
    #[error("acquisition already joined")]
    AlreadyJoined,
    /// The acquisition thread panicked; the session is lost.
    #[error("acquisition thread panicked")]
    Panicked,
    /// The thread ended and the channel is drained.
    #[error("acquisition ended: {0}")]
    Ended(String),
    /// A binding-level error (phase, busy, consumed).
    #[error(transparent)]
    Bind(#[from] BindError),
}

impl From<AcqError> for PyErr {
    /// Maps to `RuntimeError` except binding errors, which keep their typed mapping.
    fn from(e: AcqError) -> PyErr {
        match e {
            AcqError::Bind(b) => b.into(),
            other => PyRuntimeError::new_err(other.to_string()),
        }
    }
}

/// Channel capacity in blocks; always at least one.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Capacity(NonZeroUsize);

impl Capacity {
    /// Validates `n` (zero is rejected).
    pub fn new(n: usize) -> Result<Self, AcqError> {
        NonZeroUsize::new(n).map(Capacity).ok_or_else(|| {
            tracing::warn!("rejected zero channel capacity");
            AcqError::ZeroCapacity
        })
    }

    /// Capacity as a plain count.
    #[must_use]
    pub fn get(self) -> usize {
        self.0.get()
    }
}

/// Lifecycle of the acquisition thread.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AcqState {
    /// Reading and forwarding blocks.
    Streaming,
    /// Stop requested; the thread is winding down.
    Stopping,
    /// The thread ended cleanly.
    Stopped,
    /// The thread ended on a read error.
    Failed(String),
}

impl AcqState {
    /// Stable name reported to Python.
    #[must_use]
    pub fn name(&self) -> &'static str {
        match self {
            AcqState::Streaming => "STREAMING",
            AcqState::Stopping => "STOPPING",
            AcqState::Stopped => "STOPPED",
            AcqState::Failed(_) => "FAILED",
        }
    }
}

/// Point-in-time acquisition counters.
#[pyclass(frozen, module = "sadi_py.acq", name = "AcqMetrics")]
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AcqMetrics {
    /// Blocks currently queued.
    #[pyo3(get)]
    pub queue_depth: u64,
    /// Highest queue depth seen.
    #[pyo3(get)]
    pub high_water: u64,
    /// Channel capacity in blocks.
    #[pyo3(get)]
    pub capacity: u64,
    /// Blocks read from the device.
    #[pyo3(get)]
    pub blocks_read: u64,
    /// Blocks successfully queued.
    #[pyo3(get)]
    pub blocks_sent: u64,
    /// msgCount gap events seen by the decoder.
    #[pyo3(get)]
    pub gaps: u64,
    /// Data packets missing according to msgCount jumps.
    #[pyo3(get)]
    pub missed_packets: u64,
    /// Bytes the decoder dropped while resyncing.
    #[pyo3(get)]
    pub dropped_bytes: u64,
    /// Times a block found the channel full (counted once per block).
    #[pyo3(get)]
    pub channel_full_waits: u64,
    /// Total milliseconds spent waiting on a full channel.
    #[pyo3(get)]
    pub channel_full_wait_ms: u64,
    /// Blocks read but never queued (stop or consumer gone while full).
    #[pyo3(get)]
    pub blocks_lost: u64,
    /// Read timeouts (no data within the session read timeout).
    #[pyo3(get)]
    pub read_timeouts: u64,
    /// True once the channel stayed full for more than five seconds.
    #[pyo3(get)]
    pub consumer_stalled: bool,
    /// Lifecycle state name.
    #[pyo3(get)]
    pub state: &'static str,
    /// Error text when the state is FAILED.
    #[pyo3(get)]
    pub error: Option<String>,
}

#[pymethods]
impl AcqMetrics {
    /// Short summary for debugging.
    fn __repr__(&self) -> String {
        format!(
            "AcqMetrics(state={}, depth={}/{}, high_water={}, read={}, sent={}, gaps={}, full_waits={}, lost={})",
            self.state,
            self.queue_depth,
            self.capacity,
            self.high_water,
            self.blocks_read,
            self.blocks_sent,
            self.gaps,
            self.channel_full_waits,
            self.blocks_lost
        )
    }
}

/// Anything the acquisition thread can pull data blocks from.
pub trait BlockSource: Send + 'static {
    /// Reads and flattens the next block (blocking up to the source's read timeout).
    fn read_data(&mut self) -> Result<(BlockData, BlockStats), BindError>;
}

impl BlockSource for StreamParts {
    /// Delegates to the streaming session.
    fn read_data(&mut self) -> Result<(BlockData, BlockStats), BindError> {
        StreamParts::read_data(self)
    }
}

/// Counters and status shared between the reader thread and the handle.
#[derive(Debug)]
struct Shared {
    capacity: u64,
    stop: AtomicBool,
    depth: AtomicU64,
    high_water: AtomicU64,
    blocks_read: AtomicU64,
    blocks_sent: AtomicU64,
    gaps: AtomicU64,
    missed_packets: AtomicU64,
    dropped_bytes: AtomicU64,
    full_waits: AtomicU64,
    full_wait_ms: AtomicU64,
    blocks_lost: AtomicU64,
    read_timeouts: AtomicU64,
    stalled: AtomicBool,
    state: Mutex<AcqState>,
}

/// Locks `m`; the guarded data is plain state so poisoning is ignored.
fn lock<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(PoisonError::into_inner)
}

impl Shared {
    /// Fresh counters for a channel of `capacity` blocks.
    fn new(capacity: Capacity) -> Self {
        Shared {
            capacity: capacity.get() as u64,
            stop: AtomicBool::new(false),
            depth: AtomicU64::new(0),
            high_water: AtomicU64::new(0),
            blocks_read: AtomicU64::new(0),
            blocks_sent: AtomicU64::new(0),
            gaps: AtomicU64::new(0),
            missed_packets: AtomicU64::new(0),
            dropped_bytes: AtomicU64::new(0),
            full_waits: AtomicU64::new(0),
            full_wait_ms: AtomicU64::new(0),
            blocks_lost: AtomicU64::new(0),
            read_timeouts: AtomicU64::new(0),
            stalled: AtomicBool::new(false),
            state: Mutex::new(AcqState::Streaming),
        }
    }

    /// True once a stop was requested.
    fn stopping(&self) -> bool {
        self.stop.load(Ordering::Acquire)
    }

    /// Moves to `next` unless a terminal state was already recorded.
    fn set_state(&self, next: AcqState) {
        let mut st = lock(&self.state);
        if matches!(*st, AcqState::Stopped | AcqState::Failed(_)) {
            return;
        }
        tracing::info!(
            from = st.name(),
            to = next.name(),
            "acquisition state change"
        );
        *st = next;
    }

    /// Records a block that was read but could not be delivered.
    fn lose(&self, why: &str) {
        let n = self.blocks_lost.fetch_add(1, Ordering::Relaxed) + 1;
        tracing::error!(why, blocks_lost = n, "acquisition block LOST");
    }

    /// Snapshots every counter.
    fn snapshot(&self) -> AcqMetrics {
        let st = lock(&self.state).clone();
        let error = match &st {
            AcqState::Failed(e) => Some(e.clone()),
            _ => None,
        };
        let get = |a: &AtomicU64| a.load(Ordering::Relaxed);
        AcqMetrics {
            queue_depth: get(&self.depth),
            high_water: get(&self.high_water),
            capacity: self.capacity,
            blocks_read: get(&self.blocks_read),
            blocks_sent: get(&self.blocks_sent),
            gaps: get(&self.gaps),
            missed_packets: get(&self.missed_packets),
            dropped_bytes: get(&self.dropped_bytes),
            channel_full_waits: get(&self.full_waits),
            channel_full_wait_ms: get(&self.full_wait_ms),
            blocks_lost: get(&self.blocks_lost),
            read_timeouts: get(&self.read_timeouts),
            consumer_stalled: self.stalled.load(Ordering::Relaxed),
            state: st.name(),
            error,
        }
    }
}

/// Pushes `block`; on a full channel counts, logs and retries until room or stop.
/// Returns false when the consumer is gone and the thread should end.
fn deliver(shared: &Shared, tx: &SyncSender<BlockData>, block: BlockData) -> bool {
    let depth = shared.depth.fetch_add(1, Ordering::AcqRel) + 1;
    let mut pending = match tx.try_send(block) {
        Ok(()) => {
            note_sent(shared, depth);
            return true;
        }
        Err(TrySendError::Disconnected(_)) => {
            shared.depth.fetch_sub(1, Ordering::AcqRel);
            shared.lose("consumer gone");
            return false;
        }
        Err(TrySendError::Full(b)) => {
            shared.depth.fetch_sub(1, Ordering::AcqRel);
            b
        }
    };
    let waits = shared.full_waits.fetch_add(1, Ordering::Relaxed) + 1;
    tracing::error!(
        waits,
        capacity = shared.capacity,
        "acquisition channel FULL: consumer too slow; holding block, not dropping"
    );
    let started = Instant::now();
    loop {
        if shared.stopping() {
            shared.lose("stop requested while channel full");
            return true;
        }
        if started.elapsed() >= STALL_AFTER && !shared.stalled.swap(true, Ordering::Relaxed) {
            tracing::error!(
                waited_ms = started.elapsed().as_millis() as u64,
                "acquisition consumer STALLED; still blocking, never dropping"
            );
        }
        std::thread::sleep(FULL_RETRY);
        let depth = shared.depth.fetch_add(1, Ordering::AcqRel) + 1;
        match tx.try_send(pending) {
            Ok(()) => {
                let ms = started.elapsed().as_millis() as u64;
                shared.full_wait_ms.fetch_add(ms, Ordering::Relaxed);
                tracing::warn!(waited_ms = ms, "acquisition channel drained; resuming");
                note_sent(shared, depth);
                return true;
            }
            Err(TrySendError::Full(b)) => {
                shared.depth.fetch_sub(1, Ordering::AcqRel);
                pending = b;
            }
            Err(TrySendError::Disconnected(_)) => {
                shared.depth.fetch_sub(1, Ordering::AcqRel);
                shared.lose("consumer gone");
                return false;
            }
        }
    }
}

/// Updates the sent counter and high-water mark after a successful send.
fn note_sent(shared: &Shared, depth: u64) {
    shared.blocks_sent.fetch_add(1, Ordering::Relaxed);
    shared
        .high_water
        .fetch_max(depth.min(shared.capacity), Ordering::Relaxed);
}

/// Reader loop body; returns the source so the caller can resume streaming.
fn reader_loop<S: BlockSource>(mut src: S, shared: &Shared, tx: &SyncSender<BlockData>) -> S {
    tracing::info!("acquisition thread started");
    while !shared.stopping() {
        match src.read_data() {
            Ok((block, stats)) => {
                shared.blocks_read.fetch_add(1, Ordering::Relaxed);
                shared.gaps.fetch_add(stats.gap_events, Ordering::Relaxed);
                shared
                    .missed_packets
                    .fetch_add(stats.missed_packets, Ordering::Relaxed);
                shared
                    .dropped_bytes
                    .fetch_add(stats.dropped_bytes, Ordering::Relaxed);
                if stats.gap_events > 0 {
                    tracing::warn!(?stats, "msgCount gap in block");
                }
                if !deliver(shared, tx, block) {
                    break;
                }
            }
            Err(BindError::Session(SessionError::ReadTimeout(_))) => {
                shared.read_timeouts.fetch_add(1, Ordering::Relaxed);
                tracing::warn!("acquisition read timed out; retrying");
            }
            Err(e) => {
                tracing::error!(error = %e, "acquisition read failed; thread ending");
                *lock(&shared.state) = AcqState::Failed(e.to_string());
                return src;
            }
        }
    }
    shared.set_state(AcqState::Stopping);
    *lock(&shared.state) = AcqState::Stopped;
    tracing::info!("acquisition thread stopped");
    src
}

/// Handle on a running acquisition thread over source `S`.
pub struct Acq<S: BlockSource> {
    shared: Arc<Shared>,
    rx: Mutex<Receiver<BlockData>>,
    thread: Mutex<Option<JoinHandle<S>>>,
}

/// Result of one receive attempt.
#[must_use]
pub enum Recv {
    /// A block arrived.
    Block(Box<BlockData>),
    /// Nothing arrived within the timeout.
    Timeout,
}

impl<S: BlockSource> Acq<S> {
    /// Starts the reader thread over `src` with a channel of `capacity` blocks.
    pub fn spawn(src: S, capacity: Capacity) -> Result<Self, AcqError> {
        let shared = Arc::new(Shared::new(capacity));
        let (tx, rx) = sync_channel(capacity.get());
        let t_shared = Arc::clone(&shared);
        let handle = std::thread::Builder::new()
            .name("sadi-acq".into())
            .spawn(move || reader_loop(src, &t_shared, &tx))
            .map_err(AcqError::Spawn)?;
        tracing::info!(capacity = capacity.get(), "acquisition spawned");
        Ok(Acq {
            shared,
            rx: Mutex::new(rx),
            thread: Mutex::new(Some(handle)),
        })
    }

    /// Waits up to `timeout` for a block; errors once the thread ended and the queue is empty.
    pub fn recv_timeout(&self, timeout: Duration) -> Result<Recv, AcqError> {
        let rx = lock(&self.rx);
        match rx.recv_timeout(timeout) {
            Ok(b) => {
                self.shared.depth.fetch_sub(1, Ordering::AcqRel);
                Ok(Recv::Block(Box::new(b)))
            }
            Err(RecvTimeoutError::Timeout) => Ok(Recv::Timeout),
            Err(RecvTimeoutError::Disconnected) => {
                let m = self.shared.snapshot();
                tracing::info!(state = m.state, "acquisition channel drained and closed");
                Err(AcqError::Ended(
                    m.error.unwrap_or_else(|| "stopped".to_string()),
                ))
            }
        }
    }

    /// Requests a stop; the thread ends after its current read returns.
    pub fn stop(&self) {
        if !self.shared.stop.swap(true, Ordering::AcqRel) {
            tracing::info!("acquisition stop requested");
            self.shared.set_state(AcqState::Stopping);
        }
    }

    /// Current counters.
    pub fn metrics(&self) -> AcqMetrics {
        self.shared.snapshot()
    }

    /// Waits for the thread and returns the source. Call [`Acq::stop`] first or this
    /// blocks until the source fails.
    pub fn join(&self) -> Result<S, AcqError> {
        let handle = lock(&self.thread).take().ok_or(AcqError::AlreadyJoined)?;
        match handle.join() {
            Ok(src) => {
                tracing::info!("acquisition thread joined");
                Ok(src)
            }
            Err(_) => {
                tracing::error!("acquisition thread panicked");
                *lock(&self.shared.state) = AcqState::Failed("thread panicked".into());
                Err(AcqError::Panicked)
            }
        }
    }
}

impl<S: BlockSource> Drop for Acq<S> {
    /// Stops and joins a thread nobody joined, so it never outlives its handle.
    fn drop(&mut self) {
        let pending = lock(&self.thread).take();
        if let Some(h) = pending {
            tracing::warn!("acquisition dropped without join; stopping");
            self.shared.stop.store(true, Ordering::Release);
            drop(h.join());
        }
    }
}

/// Python handle on a running acquisition thread.
///
/// Construction takes the streaming stage out of the `Session` (which reports
/// busy meanwhile); `join()` hands it back so `session.stop()` can follow.
#[pyclass(frozen, module = "sadi_py.acq", name = "AcqHandle")]
pub struct AcqHandle {
    acq: Acq<StreamParts>,
    session: Py<Session>,
}

#[pymethods]
impl AcqHandle {
    /// Starts acquisition on a STREAMING `session` with a channel of `capacity` blocks.
    #[new]
    #[pyo3(signature = (session, capacity=ACQ_CHANNEL_BLOCKS))]
    fn new(session: Py<Session>, capacity: usize) -> Result<Self, AcqError> {
        let capacity = Capacity::new(capacity)?;
        let parts = session.get().take_streaming()?;
        match Acq::spawn(parts, capacity) {
            Ok(acq) => Ok(AcqHandle { acq, session }),
            Err(e) => {
                tracing::error!(error = %e, "acquisition spawn failed; session left busy");
                Err(e)
            }
        }
    }

    /// Waits (GIL released) up to `timeout_ms` for a block; None on timeout.
    ///
    /// Raises `RuntimeError` once the thread ended and the queue is drained.
    #[pyo3(signature = (timeout_ms=20))]
    fn recv_block(&self, py: Python<'_>, timeout_ms: u64) -> PyResult<Option<Block>> {
        let r = py.detach(|| self.acq.recv_timeout(Duration::from_millis(timeout_ms)))?;
        match r {
            Recv::Block(b) => b.into_py(py).map(Some),
            Recv::Timeout => Ok(None),
        }
    }

    /// Returns a queued block immediately, or None when the queue is empty.
    fn try_recv_block(&self, py: Python<'_>) -> PyResult<Option<Block>> {
        self.recv_block(py, 0)
    }

    /// Requests the thread to stop (non-blocking, idempotent).
    fn stop(&self) {
        self.acq.stop();
    }

    /// Current counters.
    fn metrics(&self) -> AcqMetrics {
        self.acq.metrics()
    }

    /// Stops, waits for the thread (GIL released), returns the session to STREAMING
    /// and yields the final counters. Blocks still queued stay receivable only until
    /// this handle is dropped.
    fn join(&self, py: Python<'_>) -> Result<AcqMetrics, AcqError> {
        self.acq.stop();
        let parts = py.detach(|| self.acq.join())?;
        self.session.get().restore_streaming(parts);
        Ok(self.acq.metrics())
    }

    /// Short summary for debugging.
    fn __repr__(&self) -> String {
        format!("AcqHandle({:?})", self.acq.metrics())
    }
}

/// Registers the `acq` submodule.
pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let sub = PyModule::new(m.py(), "acq")?;
    sub.add_class::<AcqHandle>()?;
    sub.add_class::<AcqMetrics>()?;
    sub.add("ACQ_CHANNEL_BLOCKS", ACQ_CHANNEL_BLOCKS)?;
    m.add_submodule(&sub)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::collections::VecDeque;

    use sadi_proto::codec::{AdcMode, AdcRange};
    use sadi_proto::session::{Disconnected, SessionConfig};
    use sadi_proto::sim::device::{ClockMode, SimConfig, SimDevice};
    use sadi_proto::sim::scenario::Scenario;
    use sadi_proto::{Transport, TransportError};

    use super::*;
    use crate::session::DynTransport;

    /// Scripted source: `n` blocks (every third reports a gap), then a closed transport.
    struct Script {
        left: usize,
        step: u64,
        delay: Duration,
        timeouts: VecDeque<()>,
    }

    impl Script {
        fn new(n: usize) -> Self {
            Script {
                left: n,
                step: 0,
                delay: Duration::ZERO,
                timeouts: VecDeque::new(),
            }
        }
    }

    impl BlockSource for Script {
        fn read_data(&mut self) -> Result<(BlockData, BlockStats), BindError> {
            std::thread::sleep(self.delay);
            if self.timeouts.pop_front().is_some() {
                return Err(SessionError::ReadTimeout(Duration::from_millis(1)).into());
            }
            if self.left == 0 {
                return Err(TransportError::Closed.into());
            }
            self.left -= 1;
            self.step += 1;
            let stats = BlockStats {
                gap_events: u64::from(self.step % 3 == 0),
                missed_packets: if self.step % 3 == 0 { 2 } else { 0 },
                ..BlockStats::default()
            };
            Ok((
                BlockData::new(
                    &[],
                    &[AdcRange::default(); 4],
                    AdcMode::Ideal,
                    stats,
                    None,
                    vec![],
                ),
                stats,
            ))
        }
    }

    fn cap(n: usize) -> Capacity {
        Capacity::new(n).expect("nonzero")
    }

    fn wait_until(mut f: impl FnMut() -> bool) {
        let end = Instant::now() + Duration::from_secs(5);
        while !f() {
            assert!(Instant::now() < end, "condition not reached in time");
            std::thread::sleep(Duration::from_millis(2));
        }
    }

    fn drain(acq: &Acq<Script>) -> u64 {
        let mut n = 0;
        while let Ok(r) = acq.recv_timeout(Duration::from_millis(50)) {
            if matches!(r, Recv::Block(_)) {
                n += 1;
            }
        }
        n
    }

    // frob:tests crates/sadi-py/src/acq.rs::Capacity
    #[test]
    fn zero_capacity_rejected() {
        assert!(matches!(Capacity::new(0), Err(AcqError::ZeroCapacity)));
        assert_eq!(cap(4).get(), 4);
    }

    // frob:tests crates/sadi-py/src/acq.rs::Acq
    // frob:tests crates/sadi-py/src/acq.rs::deliver
    #[test]
    fn full_channel_is_counted_and_lossless() {
        let acq = Acq::spawn(Script::new(10), cap(2)).expect("spawn");
        wait_until(|| acq.metrics().channel_full_waits >= 1);
        let m = acq.metrics();
        assert_eq!(m.queue_depth, 2);
        assert_eq!(m.high_water, 2);
        assert_eq!(m.blocks_read, 3, "third block held, not dropped");
        assert_eq!(m.blocks_lost, 0);
        assert_eq!(drain(&acq), 10);
        let m = acq.metrics();
        assert_eq!((m.blocks_read, m.blocks_sent, m.blocks_lost), (10, 10, 0));
        assert_eq!(m.queue_depth, 0);
        assert!(m.channel_full_waits >= 1);
        assert_eq!(m.state, "FAILED");
        assert!(acq.join().is_ok());
    }

    // frob:tests crates/sadi-py/src/acq.rs::reader_loop
    #[test]
    fn gaps_and_timeouts_are_counted() {
        let mut s = Script::new(6);
        s.timeouts.push_back(());
        s.timeouts.push_back(());
        let acq = Acq::spawn(s, cap(16)).expect("spawn");
        assert_eq!(drain(&acq), 6);
        let m = acq.metrics();
        assert_eq!(m.gaps, 2);
        assert_eq!(m.missed_packets, 4);
        assert_eq!(m.read_timeouts, 2);
        assert!(m.error.is_some_and(|e| e.contains("closed")));
    }

    // frob:tests crates/sadi-py/src/acq.rs::Acq.stop
    // frob:tests crates/sadi-py/src/acq.rs::Acq.join
    #[test]
    fn stop_while_full_counts_lost_and_joins() {
        let acq = Acq::spawn(Script::new(100), cap(1)).expect("spawn");
        wait_until(|| acq.metrics().channel_full_waits >= 1);
        acq.stop();
        let src = acq.join().expect("join");
        assert_eq!(src.left, 100 - 2);
        let m = acq.metrics();
        assert_eq!(m.blocks_lost, 1, "unsent block counted, never silent");
        assert_eq!(m.state, "STOPPED");
        assert!(matches!(acq.join(), Err(AcqError::AlreadyJoined)));
    }

    // frob:tests crates/sadi-py/src/acq.rs::Acq.recv_timeout
    #[test]
    fn recv_times_out_then_ends() {
        let mut s = Script::new(0);
        s.delay = Duration::from_millis(200);
        let acq = Acq::spawn(s, cap(2)).expect("spawn");
        assert!(matches!(
            acq.recv_timeout(Duration::from_millis(5)),
            Ok(Recv::Timeout)
        ));
        assert!(matches!(
            acq.recv_timeout(Duration::from_secs(2)),
            Err(AcqError::Ended(_))
        ));
    }

    /// A STREAMING sadi-proto session over a real-time (paced) simulator.
    fn paced_sim() -> StreamParts {
        let sc = Scenario::builtin("clean").expect("scenario");
        let sim = SimDevice::new(
            Box::new(sc),
            SimConfig::default().with_clock(ClockMode::Paced),
        );
        let t = DynTransport(Box::new(sim) as Box<dyn Transport>);
        let connected = Disconnected::new(t, SessionConfig::default())
            .connect()
            .map_err(|e| e.to_string())
            .expect("connect");
        let streaming = connected
            .start([AdcRange::default(); 4])
            .map_err(|e| e.to_string())
            .expect("start");
        StreamParts::new(streaming, AdcMode::Ideal, Arc::default())
    }

    // frob:tests crates/sadi-py/src/acq.rs::AcqHandle
    // frob:tests crates/sadi-py/src/acq.rs::Acq.spawn
    #[test]
    fn realtime_sim_with_slow_consumer_loses_nothing() {
        let acq = Acq::spawn(paced_sim(), cap(4)).expect("spawn");
        let run = Duration::from_millis(1500);
        let start = Instant::now();
        let mut got = 0u64;
        while start.elapsed() < run {
            // Deliberately slow: the sim produces about one block per millisecond.
            if let Ok(Recv::Block(_)) = acq.recv_timeout(Duration::from_millis(50)) {
                got += 1;
                std::thread::sleep(Duration::from_millis(10));
            }
        }
        acq.stop();
        let parts = acq.join().expect("join");
        let m = acq.metrics();
        assert!(
            m.channel_full_waits > 0,
            "slow consumer must hit a full channel: {m:?}"
        );
        assert_eq!(m.high_water, 4);
        assert_eq!(
            m.gaps, 0,
            "blocking, not dropping, keeps the stream gap free"
        );
        assert_eq!(m.dropped_bytes, 0);
        assert!(
            m.blocks_lost <= 1,
            "at most the in-flight block at stop: {m:?}"
        );
        // Everything read was either received, still queued, or the one counted lost.
        assert_eq!(m.blocks_read, m.blocks_sent + m.blocks_lost);
        assert_eq!(got + m.queue_depth, m.blocks_sent);
        // The thread was throttled to the consumer, far below real-time production.
        assert!(got < 400, "consumer was slow, got {got}");
        drop(parts);
    }
}
