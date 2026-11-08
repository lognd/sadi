//! Device entry points: `open_serial`, `open_sim`, `ports` and `SessionConfig`.
//!
//! Nothing about the (unverified) wire protocol is hard-coded here: every
//! timing and handshake choice is an optional field that falls back to
//! sadi-proto's documented defaults.
// frob:ticket 01M6W7R226VMAMHYPDBQTAS277

use std::time::Duration;

use pyo3::prelude::*;
use sadi_proto::serial::{
    list_ports, BaudRate, IoTimeout, RxLimit, SerialConfig, SerialTransport, FTDI_ALLOW_LIST,
};
use sadi_proto::session::{CommandPolicy, ReadTimeout, SessionConfig as ProtoConfig};
use sadi_proto::sim::device::{SimConfig, SimDevice};
use sadi_proto::sim::scenario::Scenario;
use sadi_proto::Transport;

use crate::convert::{PyHandshake, PyIdempotence};
use crate::errors::BindError;
use crate::session::Session;

/// Optional overrides for session timing and serial parameters.
///
/// Unset fields keep sadi-proto defaults. `command_interval_ms` and
/// `command_timeout_ms` must be given together and apply to all four commands.
#[pyclass(frozen, from_py_object, module = "sadi_py", name = "SessionConfig")]
#[derive(Clone, Debug, Default)]
pub struct SessionConfig {
    /// Data-block read timeout in milliseconds.
    #[pyo3(get)]
    read_timeout_ms: Option<u64>,
    /// Command retry interval in milliseconds.
    #[pyo3(get)]
    command_interval_ms: Option<u64>,
    /// Command overall timeout in milliseconds.
    #[pyo3(get)]
    command_timeout_ms: Option<u64>,
    /// Start/Stop idempotence override.
    #[pyo3(get)]
    idempotence: Option<PyIdempotence>,
    /// Handshake override.
    #[pyo3(get)]
    handshake: Option<PyHandshake>,
    /// Serial baud rate (serial only).
    #[pyo3(get)]
    baud: Option<u32>,
    /// Serial per-read timeout in milliseconds (serial only).
    #[pyo3(get)]
    io_timeout_ms: Option<u64>,
    /// Serial receive buffer limit in bytes (serial only).
    #[pyo3(get)]
    rx_limit: Option<usize>,
}

#[pymethods]
impl SessionConfig {
    /// Builds a config; every argument is optional and keyword-only.
    #[new]
    #[pyo3(signature = (*, read_timeout_ms=None, command_interval_ms=None, command_timeout_ms=None,
                        idempotence=None, handshake=None, baud=None, io_timeout_ms=None, rx_limit=None))]
    #[allow(clippy::too_many_arguments)]
    fn new(
        read_timeout_ms: Option<u64>,
        command_interval_ms: Option<u64>,
        command_timeout_ms: Option<u64>,
        idempotence: Option<PyIdempotence>,
        handshake: Option<PyHandshake>,
        baud: Option<u32>,
        io_timeout_ms: Option<u64>,
        rx_limit: Option<usize>,
    ) -> Result<Self, BindError> {
        if command_interval_ms.is_some() != command_timeout_ms.is_some() {
            return Err(BindError::Config(
                "command_interval_ms and command_timeout_ms must be given together".into(),
            ));
        }
        Ok(SessionConfig {
            read_timeout_ms,
            command_interval_ms,
            command_timeout_ms,
            idempotence,
            handshake,
            baud,
            io_timeout_ms,
            rx_limit,
        })
    }

    /// Short summary for debugging.
    fn __repr__(&self) -> String {
        format!("SessionConfig({self:?})")
    }
}

impl SessionConfig {
    /// Applies the overrides onto sadi-proto's defaults.
    fn to_proto(&self) -> Result<ProtoConfig, BindError> {
        let mut cfg = ProtoConfig::default();
        if let Some(ms) = self.read_timeout_ms {
            cfg = cfg.with_read_timeout(ReadTimeout::from_millis(ms)?);
        }
        if let (Some(i), Some(t)) = (self.command_interval_ms, self.command_timeout_ms) {
            cfg = cfg.with_all_policies(CommandPolicy::from_millis(i, t)?);
        }
        if let Some(i) = self.idempotence {
            cfg = cfg.with_idempotence(i.into());
        }
        if let Some(h) = self.handshake {
            cfg = cfg.with_handshake(h.into());
        }
        Ok(cfg)
    }

    /// Builds the serial configuration for `port`.
    fn to_serial(&self, port: &str) -> Result<SerialConfig, BindError> {
        let mut s = SerialConfig::new(port)?;
        if let Some(b) = self.baud {
            s = s.with_baud(BaudRate::new(b)?);
        }
        if let Some(ms) = self.io_timeout_ms {
            s = s.with_timeout(IoTimeout::new(Duration::from_millis(ms))?);
        }
        if let Some(n) = self.rx_limit {
            s = s.with_rx_limit(RxLimit::new(n)?);
        }
        Ok(s)
    }
}

/// A serial port that passed the FTDI allow-list.
#[pyclass(frozen, module = "sadi_py", name = "PortInfo")]
pub struct PortInfo {
    /// OS port name or path.
    #[pyo3(get)]
    name: String,
    /// USB vendor id.
    #[pyo3(get)]
    vid: u16,
    /// USB product id.
    #[pyo3(get)]
    pid: u16,
    /// USB product string, if reported.
    #[pyo3(get)]
    product: Option<String>,
}

#[pymethods]
impl PortInfo {
    /// Short summary for debugging.
    fn __repr__(&self) -> String {
        format!("PortInfo({}, {:04x}:{:04x})", self.name, self.vid, self.pid)
    }
}

/// Lists attached serial ports matching the FTDI allow-list.
#[pyfunction]
pub fn ports(py: Python<'_>) -> Result<Vec<PortInfo>, BindError> {
    let found = py.detach(|| list_ports(&FTDI_ALLOW_LIST))?;
    tracing::info!(count = found.len(), "serial ports listed");
    Ok(found
        .iter()
        .map(|p| PortInfo {
            name: p.name().to_owned(),
            vid: p.id().vid(),
            pid: p.id().pid(),
            product: p.product().map(str::to_owned),
        })
        .collect())
}

/// Opens a serial port and returns a DISCONNECTED session.
#[pyfunction]
#[pyo3(signature = (port, cfg=None))]
pub fn open_serial(
    py: Python<'_>,
    port: &str,
    cfg: Option<SessionConfig>,
) -> Result<Session, BindError> {
    let cfg = cfg.unwrap_or_default();
    let proto = cfg.to_proto()?;
    let serial = cfg.to_serial(port)?;
    let transport = py.detach(|| SerialTransport::open(&serial))?;
    tracing::info!(port, "serial transport opened");
    Ok(Session::new(
        Box::new(transport) as Box<dyn Transport>,
        proto,
    ))
}

/// Opens a simulated device and returns a DISCONNECTED session.
///
/// `scenario` is JSON text (starts with `{`) or a builtin scenario name. A
/// `seed` replaces the scenario's fault-plan seed for reproducible noise.
#[pyfunction]
#[pyo3(signature = (scenario, seed=None, cfg=None))]
pub fn open_sim(
    scenario: &str,
    seed: Option<u64>,
    cfg: Option<SessionConfig>,
) -> Result<Session, BindError> {
    let proto = cfg.unwrap_or_default().to_proto()?;
    let mut sc = if scenario.trim_start().starts_with('{') {
        Scenario::from_json(scenario)?
    } else {
        Scenario::builtin(scenario)?
    };
    if let Some(seed) = seed {
        let faults = sc.faults.clone().with_seed(seed);
        sc = sc.with_faults(faults);
    }
    let sim = SimDevice::new(Box::new(sc), SimConfig::default());
    tracing::info!(?seed, "simulator opened");
    Ok(Session::new(Box::new(sim) as Box<dyn Transport>, proto))
}
