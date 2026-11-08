//! The Python `Session`: a runtime-phased wrapper over sadi-proto's typestate session.
//!
//! sadi-proto's phases are distinct Rust types and invalid transitions do not
//! compile. Python cannot see types, so the wrapper keeps the live phase handle
//! in a `Slot`: `Idle(stage)`, `Busy` (a blocking call holds the stage with the
//! GIL released) or `Consumed` (closed). Every call moves the stage out, runs
//! the transition, and moves the successor back, so a handle can never be used
//! twice or concurrently; misuse raises a typed Python error instead.
// frob:ticket 01M6W7R226VMAMHYPDBQTAS277

use std::sync::{Arc, Mutex, MutexGuard, PoisonError};
use std::time::Duration;

use pyo3::prelude::*;
use sadi_proto::codec::{AdcMode, AdcRange, DeviceState, VersionPacket};
use sadi_proto::session::{
    BlockStats, Connected, Disconnected, SessionConfig, Stopped, Streaming, TapError,
};
use sadi_proto::{Transport, TransportError};

use crate::convert::{Block, BlockData, Phase, PyAdcMode, PyAdcRange, PyDeviceState};
use crate::errors::BindError;

/// Object-safe transport adapter so one session type serves serial and simulator.
pub(crate) struct DynTransport(pub(crate) Box<dyn Transport>);

impl Transport for DynTransport {
    /// Delegates to the boxed transport.
    fn write_all(&mut self, data: &[u8]) -> Result<(), TransportError> {
        self.0.write_all(data)
    }

    /// Delegates to the boxed transport.
    fn read(&mut self, buf: &mut [u8], timeout: Duration) -> Result<usize, TransportError> {
        self.0.read(buf, timeout)
    }

    /// Delegates to the boxed transport.
    fn purge(&mut self) -> Result<(), TransportError> {
        self.0.purge()
    }

    /// Delegates to the boxed transport.
    fn close(&mut self) -> Result<(), TransportError> {
        self.0.close()
    }

    /// Delegates to the boxed transport.
    fn description(&self) -> String {
        self.0.description()
    }
}

/// The live phase handle of a session.
enum Stage {
    Disconnected(Disconnected<DynTransport>),
    Connected(Connected<DynTransport>),
    Streaming(Streaming<DynTransport>, AdcMode),
    Stopped(Stopped<DynTransport>),
}

impl Stage {
    /// Returns the Python-visible phase of this stage.
    fn phase(&self) -> Phase {
        match self {
            Stage::Disconnected(_) => Phase::Disconnected,
            Stage::Connected(_) => Phase::Connected,
            Stage::Streaming(..) => Phase::Streaming,
            Stage::Stopped(_) => Phase::Stopped,
        }
    }
}

/// Runtime linearity cell: the stage is present, in use, or gone.
enum Slot {
    Idle(Stage),
    Busy,
    Consumed,
}

/// Outcome of one transition: the successor slot and the call's result.
type Step<R> = (Slot, Result<R, BindError>);

/// Rejects a call made in the wrong phase, leaving the stage untouched.
fn wrong<R>(stage: Stage, expected: &'static str) -> Step<R> {
    let actual = stage.phase().as_str();
    tracing::warn!(expected, actual, "call rejected: wrong phase");
    (
        Slot::Idle(stage),
        Err(BindError::Phase { expected, actual }),
    )
}

/// Locks `m`, recovering the data if a panic poisoned it (state is plain data).
fn lock<T>(m: &Mutex<T>) -> MutexGuard<'_, T> {
    m.lock().unwrap_or_else(PoisonError::into_inner)
}

/// Drains the raw-byte buffer filled by the tap.
fn take_raw(raw: &Mutex<Vec<u8>>) -> Vec<u8> {
    std::mem::take(&mut *lock(raw))
}

/// Version packet contents returned by `query()` and `reset()`.
#[pyclass(frozen, module = "sadi_py", name = "VersionInfo")]
pub struct VersionInfo {
    /// Device state reported.
    #[pyo3(get)]
    state: PyDeviceState,
    /// Raw device state byte.
    #[pyo3(get)]
    state_byte: u8,
    /// Firmware major version.
    #[pyo3(get)]
    major: u16,
    /// Firmware minor version.
    #[pyo3(get)]
    minor: u16,
}

impl From<VersionPacket> for VersionInfo {
    /// Copies the fields out of the decoded packet.
    fn from(v: VersionPacket) -> Self {
        VersionInfo {
            state: v.state.into(),
            state_byte: v.state.to_byte(),
            major: v.major,
            minor: v.minor,
        }
    }
}

#[pymethods]
impl VersionInfo {
    /// Firmware version as `major.minor` float, as the vendor tools print it.
    #[getter]
    fn fw_version(&self) -> f64 {
        VersionPacket {
            state: DeviceState::from_byte(self.state_byte),
            major: self.major,
            minor: self.minor,
        }
        .fw_version()
    }

    /// Short summary for debugging.
    fn __repr__(&self) -> String {
        format!(
            "VersionInfo(major={}, minor={}, state_byte={})",
            self.major, self.minor, self.state_byte
        )
    }
}

/// A device session; move-only in spirit, enforced at runtime.
///
/// Phases: DISCONNECTED -> `connect()` -> CONNECTED -> `start()` -> STREAMING
/// -> `stop()` -> STOPPED -> `close()` -> CLOSED (any later call raises
/// `ConsumedError`). A blocking call releases the GIL; a second call from
/// another thread meanwhile raises `BusyError`.
#[pyclass(frozen, module = "sadi_py", name = "Session")]
pub struct Session {
    slot: Mutex<Slot>,
    raw: Arc<Mutex<Vec<u8>>>,
    description: String,
}

impl Session {
    /// Wraps `transport` in a Disconnected sadi-proto session with a raw-byte tap.
    pub(crate) fn new(transport: Box<dyn Transport>, config: SessionConfig) -> Self {
        let description = transport.description();
        let raw = Arc::new(Mutex::new(Vec::new()));
        let tap_raw = Arc::clone(&raw);
        let tap = move |bytes: &[u8]| -> Result<(), TapError> {
            match tap_raw.lock() {
                Ok(mut buf) => {
                    buf.extend_from_slice(bytes);
                    Ok(())
                }
                Err(_) => Err(TapError::new("raw byte buffer lock poisoned")),
            }
        };
        let inner = Disconnected::new(DynTransport(transport), config).with_tap(Box::new(tap));
        tracing::info!(%description, "python session created");
        Session {
            slot: Mutex::new(Slot::Idle(Stage::Disconnected(inner))),
            raw,
            description,
        }
    }

    /// Moves the stage out, runs `f` with the GIL released, and stores the successor.
    fn run<R: Send>(
        &self,
        py: Python<'_>,
        f: impl FnOnce(Stage) -> Step<R> + Send,
    ) -> Result<R, BindError> {
        let stage = {
            let mut g = lock(&self.slot);
            match std::mem::replace(&mut *g, Slot::Busy) {
                Slot::Idle(s) => s,
                Slot::Busy => return Err(BindError::Busy),
                Slot::Consumed => {
                    *g = Slot::Consumed;
                    return Err(BindError::Consumed);
                }
            }
        };
        let (next, result) = py.detach(move || f(stage));
        *lock(&self.slot) = next;
        result
    }

    /// Stops a streaming session and returns the trailing block (internal for `__exit__`).
    fn stop_inner(&self, py: Python<'_>) -> Result<BlockData, BindError> {
        let raw = Arc::clone(&self.raw);
        self.run(py, move |stage| match stage {
            Stage::Streaming(s, mode) => {
                let ranges = *s.ranges();
                match s.stop() {
                    Ok(mut stopped) => {
                        let trailing = stopped.take_trailing();
                        let data = BlockData::new(
                            &trailing,
                            &ranges,
                            mode,
                            BlockStats::default(),
                            Some(DeviceState::Stopped),
                            take_raw(&raw),
                        );
                        (Slot::Idle(Stage::Stopped(stopped)), Ok(data))
                    }
                    Err(te) => {
                        let (e, s) = te.into_parts();
                        (Slot::Idle(Stage::Streaming(s, mode)), Err(e.into()))
                    }
                }
            }
            other => wrong(other, "streaming"),
        })
    }

    /// Closes the transport from any non-streaming phase and consumes the handle.
    fn close_inner(&self, py: Python<'_>) -> Result<(), BindError> {
        self.run(py, |stage| {
            let closed = |mut t: DynTransport| {
                let r = t.close().map_err(BindError::from);
                tracing::info!("python session closed");
                (Slot::Consumed, r)
            };
            match stage {
                Stage::Disconnected(d) => closed(d.into_transport()),
                Stage::Connected(c) => closed(c.disconnect().into_transport()),
                Stage::Stopped(s) => match s.close() {
                    Ok(_transport) => {
                        tracing::info!("python session closed");
                        (Slot::Consumed, Ok(()))
                    }
                    Err(te) => {
                        let (e, s) = te.into_parts();
                        (Slot::Idle(Stage::Stopped(s)), Err(e.into()))
                    }
                },
                other @ Stage::Streaming(..) => wrong(other, "disconnected, connected or stopped"),
            }
        })
    }
}

#[pymethods]
impl Session {
    /// Current phase; `CLOSED` once consumed.
    #[getter]
    fn phase(&self) -> Result<Phase, BindError> {
        match &*lock(&self.slot) {
            Slot::Idle(s) => Ok(s.phase()),
            Slot::Busy => Err(BindError::Busy),
            Slot::Consumed => Ok(Phase::Closed),
        }
    }

    /// Human-readable transport description (port name or simulator).
    #[getter]
    fn description(&self) -> &str {
        &self.description
    }

    /// Runs the handshake; DISCONNECTED -> CONNECTED. On failure the phase is unchanged.
    fn connect(&self, py: Python<'_>) -> Result<(), BindError> {
        self.run(py, |stage| match stage {
            Stage::Disconnected(d) => match d.connect() {
                Ok(c) => (Slot::Idle(Stage::Connected(c)), Ok(())),
                Err(te) => {
                    let (e, d) = te.into_parts();
                    (Slot::Idle(Stage::Disconnected(d)), Err(e.into()))
                }
            },
            other => wrong(other, "disconnected"),
        })
    }

    /// Sends Query and returns the version packet; needs CONNECTED.
    fn query(&self, py: Python<'_>) -> Result<VersionInfo, BindError> {
        self.run(py, |stage| match stage {
            Stage::Connected(mut c) => {
                let r = c.query().map(VersionInfo::from).map_err(BindError::from);
                (Slot::Idle(Stage::Connected(c)), r)
            }
            other => wrong(other, "connected"),
        })
    }

    /// Sends Reset and returns the boot version packet; needs CONNECTED.
    fn reset(&self, py: Python<'_>) -> Result<VersionInfo, BindError> {
        self.run(py, |stage| match stage {
            Stage::Connected(mut c) => {
                let r = c.reset().map(VersionInfo::from).map_err(BindError::from);
                (Slot::Idle(Stage::Connected(c)), r)
            }
            other => wrong(other, "connected"),
        })
    }

    /// Starts streaming; CONNECTED -> STREAMING.
    ///
    /// `adc_mode` selects the raw-to-volts formula and has no default. `ranges`
    /// is four `AdcRange` values (channels 0..3); omitted means +-5.12 V each.
    #[pyo3(signature = (adc_mode, ranges=None))]
    fn start(
        &self,
        py: Python<'_>,
        adc_mode: PyAdcMode,
        ranges: Option<Vec<PyAdcRange>>,
    ) -> Result<(), BindError> {
        let ranges: [AdcRange; 4] = match ranges {
            None => [AdcRange::default(); 4],
            Some(v) => {
                let n = v.len();
                let four: [PyAdcRange; 4] = v
                    .try_into()
                    .map_err(|_| BindError::Config(format!("ranges needs 4 entries, got {n}")))?;
                four.map(AdcRange::from)
            }
        };
        let mode = AdcMode::from(adc_mode);
        self.run(py, move |stage| match stage {
            Stage::Connected(c) => match c.start(ranges) {
                Ok(s) => (Slot::Idle(Stage::Streaming(s, mode)), Ok(())),
                Err(te) => {
                    let (e, c) = te.into_parts();
                    (Slot::Idle(Stage::Connected(c)), Err(e.into()))
                }
            },
            other => wrong(other, "connected"),
        })
    }

    /// Blocks (GIL released) for the next data block.
    ///
    /// Returns the decoded numpy columns and every raw wire byte read since the
    /// previous call, so the caller can persist `raw` before using the arrays.
    /// On error the raw bytes stay buffered and arrive with the next block.
    fn read_block(&self, py: Python<'_>) -> PyResult<Block> {
        let raw = Arc::clone(&self.raw);
        let data = self.run(py, move |stage| match stage {
            Stage::Streaming(mut s, mode) => {
                let result = match s.read_block() {
                    Ok(b) => Ok(BlockData::new(
                        b.packets(),
                        s.ranges(),
                        mode,
                        b.stats(),
                        b.device_state(),
                        take_raw(&raw),
                    )),
                    Err(e) => Err(e.into()),
                };
                (Slot::Idle(Stage::Streaming(s, mode)), result)
            }
            other => wrong(other, "streaming"),
        })?;
        data.into_py(py)
    }

    /// Stops streaming; STREAMING -> STOPPED. Returns the trailing block (maybe empty).
    fn stop(&self, py: Python<'_>) -> PyResult<Block> {
        self.stop_inner(py)?.into_py(py)
    }

    /// Returns STOPPED to CONNECTED without a new handshake.
    fn restart(&self, py: Python<'_>) -> Result<(), BindError> {
        self.run(py, |stage| match stage {
            Stage::Stopped(s) => (Slot::Idle(Stage::Connected(s.restart())), Ok(())),
            other => wrong(other, "stopped"),
        })
    }

    /// Returns CONNECTED to DISCONNECTED (the next connect repeats the handshake).
    fn disconnect(&self, py: Python<'_>) -> Result<(), BindError> {
        self.run(py, |stage| match stage {
            Stage::Connected(c) => (Slot::Idle(Stage::Disconnected(c.disconnect())), Ok(())),
            other => wrong(other, "connected"),
        })
    }

    /// Closes the transport and consumes the handle; stop streaming first.
    fn close(&self, py: Python<'_>) -> Result<(), BindError> {
        self.close_inner(py)
    }

    /// Context-manager entry; returns the session itself.
    fn __enter__(slf: PyRef<'_, Self>) -> PyRef<'_, Self> {
        slf
    }

    /// Context-manager exit: stop if streaming, then close; cleanup errors are
    /// raised only when no other exception is propagating.
    #[pyo3(signature = (exc_type=None, _exc=None, _tb=None))]
    fn __exit__(
        &self,
        py: Python<'_>,
        exc_type: Option<&Bound<'_, PyAny>>,
        _exc: Option<&Bound<'_, PyAny>>,
        _tb: Option<&Bound<'_, PyAny>>,
    ) -> Result<bool, BindError> {
        let streaming = matches!(&*lock(&self.slot), Slot::Idle(Stage::Streaming(..)));
        let mut outcome = Ok(());
        if streaming {
            outcome = self.stop_inner(py).map(drop);
        }
        let closed = match &outcome {
            Ok(()) => self.close_inner(py),
            Err(_) => Ok(()),
        };
        let cleanup = outcome.and(closed.or_else(|e| match e {
            BindError::Consumed => Ok(()),
            other => Err(other),
        }));
        match (cleanup, exc_type) {
            (Err(e), None) => Err(e),
            (Err(e), Some(_)) => {
                tracing::warn!(error = %e, "cleanup failed while an exception propagates");
                Ok(false)
            }
            (Ok(()), _) => Ok(false),
        }
    }

    /// Short summary for debugging.
    fn __repr__(&self) -> String {
        let phase = match &*lock(&self.slot) {
            Slot::Idle(s) => s.phase().as_str(),
            Slot::Busy => "busy",
            Slot::Consumed => "closed",
        };
        format!("Session({}, phase={phase})", self.description)
    }
}
