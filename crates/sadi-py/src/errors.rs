//! Rust-to-Python error mapping: one binding error enum, one exception hierarchy.
//!
//! Every Python exception raised by this crate derives from `SadiError` and
//! carries `.kind` (a stable machine-readable string) and `.detail` (the
//! human-readable message). Matches over foreign `#[non_exhaustive]` enums
//! need one wildcard arm; it maps to kind `"other"` and logs a warning so a
//! new upstream variant is noticed rather than silently renamed.
// frob:ticket 01M6W7R226VMAMHYPDBQTAS277

use pyo3::exceptions::PyException;
use pyo3::prelude::*;
use sadi_proto::codec::CodecError;
use sadi_proto::serial::SerialConfigError;
use sadi_proto::session::{ConfigError, SessionError};
use sadi_proto::sim::device::SimError;
use sadi_proto::sim::scenario::ScenarioError;
use sadi_proto::TransportError;

pyo3::create_exception!(
    _native,
    SadiError,
    PyException,
    "Base class of every sadi_py error."
);
pyo3::create_exception!(
    _native,
    ConfigurationError,
    SadiError,
    "Invalid configuration value."
);
pyo3::create_exception!(
    _native,
    TransportFailure,
    SadiError,
    "The byte transport failed."
);
pyo3::create_exception!(
    _native,
    CommandTimeoutError,
    SadiError,
    "A device command went unanswered."
);
pyo3::create_exception!(
    _native,
    ReadTimeoutError,
    SadiError,
    "No data block arrived in time."
);
pyo3::create_exception!(
    _native,
    UnexpectedStateError,
    SadiError,
    "The device is in the wrong state."
);
pyo3::create_exception!(
    _native,
    TapError,
    SadiError,
    "The raw-byte tap refused bytes."
);
pyo3::create_exception!(
    _native,
    CodecFailure,
    SadiError,
    "Bytes did not form a valid frame."
);
pyo3::create_exception!(
    _native,
    ScenarioFailure,
    SadiError,
    "The simulator scenario is invalid."
);
pyo3::create_exception!(
    _native,
    PhaseError,
    SadiError,
    "Operation not valid in the session's phase."
);
pyo3::create_exception!(
    _native,
    ConsumedError,
    SadiError,
    "The session handle was already consumed."
);
pyo3::create_exception!(
    _native,
    BusyError,
    SadiError,
    "The session is in use by another call."
);

/// Every failure this crate can raise, before conversion to a Python exception.
#[derive(Debug, thiserror::Error)]
pub enum BindError {
    /// Invalid configuration value from Python.
    #[error("{0}")]
    Config(String),
    /// Session-level configuration rejected by sadi-proto.
    #[error("{0}")]
    SessionConfig(#[from] ConfigError),
    /// Serial configuration rejected by sadi-proto.
    #[error("{0}")]
    SerialConfig(#[from] SerialConfigError),
    /// Transport failure outside a session call.
    #[error("{0}")]
    Transport(#[from] TransportError),
    /// Session operation failure.
    #[error("{0}")]
    Session(#[from] SessionError),
    /// Frame encode/decode failure.
    #[error("{0}")]
    Codec(#[from] CodecError),
    /// Simulator construction failure.
    #[error("{0}")]
    Sim(#[from] SimError),
    /// Scenario parse/validation failure.
    #[error("{0}")]
    Scenario(#[from] ScenarioError),
    /// The call needs a different phase than the session is in.
    #[error("operation needs phase {expected}, session is {actual}")]
    Phase {
        /// Phase(s) the operation is valid in.
        expected: &'static str,
        /// Phase the session is in.
        actual: &'static str,
    },
    /// The session was closed; no further call is possible.
    #[error("session handle was consumed by close()")]
    Consumed,
    /// Another thread is inside a blocking call on this session.
    #[error("session is busy in another call")]
    Busy,
    /// The built-in self-test found a disagreement.
    #[error("self-test failed: {0}")]
    SelfTest(String),
}

/// Stable machine-readable kind strings (also listed in `__init__.pyi`).
pub mod kind {
    /// Invalid configuration.
    pub const CONFIG: &str = "config";
    /// Transport read timeout.
    pub const TRANSPORT_TIMEOUT: &str = "transport_timeout";
    /// Transport closed or device vanished.
    pub const TRANSPORT_CLOSED: &str = "transport_closed";
    /// Receive overflow.
    pub const TRANSPORT_OVERFLOW: &str = "transport_overflow";
    /// OS or driver I/O failure.
    pub const TRANSPORT_IO: &str = "transport_io";
    /// Command timeout.
    pub const COMMAND_TIMEOUT: &str = "command_timeout";
    /// Read timeout.
    pub const READ_TIMEOUT: &str = "read_timeout";
    /// Unexpected device state.
    pub const UNEXPECTED_STATE: &str = "unexpected_state";
    /// Raw tap failure.
    pub const TAP: &str = "tap";
    /// Codec failure.
    pub const CODEC: &str = "codec";
    /// Scenario failure.
    pub const SCENARIO: &str = "scenario";
    /// Wrong phase.
    pub const PHASE: &str = "phase";
    /// Consumed handle.
    pub const CONSUMED: &str = "consumed";
    /// Busy session.
    pub const BUSY: &str = "busy";
    /// An upstream variant this binding does not know yet.
    pub const OTHER: &str = "other";
}

/// Maps a transport error to its kind string.
fn transport_kind(e: &TransportError) -> &'static str {
    match e {
        TransportError::Timeout(_) => kind::TRANSPORT_TIMEOUT,
        TransportError::Closed => kind::TRANSPORT_CLOSED,
        TransportError::Overflow { .. } => kind::TRANSPORT_OVERFLOW,
        TransportError::Io(_) => kind::TRANSPORT_IO,
        // Foreign #[non_exhaustive]: the one unavoidable wildcard.
        #[allow(clippy::wildcard_enum_match_arm)]
        _ => {
            tracing::warn!(error = %e, "unmapped TransportError variant");
            kind::OTHER
        }
    }
}

impl BindError {
    /// Returns the stable kind string for this error.
    #[must_use]
    pub fn kind(&self) -> &'static str {
        match self {
            BindError::Config(_) | BindError::SessionConfig(_) | BindError::SerialConfig(_) => {
                kind::CONFIG
            }
            BindError::Transport(t) => transport_kind(t),
            BindError::Session(s) => match s {
                SessionError::Transport(t) => transport_kind(t),
                SessionError::CommandTimeout { .. } => kind::COMMAND_TIMEOUT,
                SessionError::ReadTimeout(_) => kind::READ_TIMEOUT,
                SessionError::UnexpectedState { .. } => kind::UNEXPECTED_STATE,
                SessionError::Tap(_) => kind::TAP,
            },
            BindError::Codec(_) | BindError::SelfTest(_) => kind::CODEC,
            BindError::Sim(SimError::ZeroSampleRate) => kind::CONFIG,
            BindError::Sim(SimError::Scenario(_)) | BindError::Scenario(_) => kind::SCENARIO,
            BindError::Phase { .. } => kind::PHASE,
            BindError::Consumed => kind::CONSUMED,
            BindError::Busy => kind::BUSY,
        }
    }

    /// Builds the Python exception of the matching class with `.kind` and `.detail`.
    fn into_pyerr(self, py: Python<'_>) -> PyErr {
        let kind = self.kind();
        let detail = self.to_string();
        let err = match &self {
            BindError::Config(_) | BindError::SessionConfig(_) | BindError::SerialConfig(_) => {
                ConfigurationError::new_err(detail.clone())
            }
            BindError::Transport(_) => TransportFailure::new_err(detail.clone()),
            BindError::Session(s) => match s {
                SessionError::Transport(_) => TransportFailure::new_err(detail.clone()),
                SessionError::CommandTimeout { .. } => CommandTimeoutError::new_err(detail.clone()),
                SessionError::ReadTimeout(_) => ReadTimeoutError::new_err(detail.clone()),
                SessionError::UnexpectedState { .. } => {
                    UnexpectedStateError::new_err(detail.clone())
                }
                SessionError::Tap(_) => TapError::new_err(detail.clone()),
            },
            BindError::Codec(_) | BindError::SelfTest(_) => CodecFailure::new_err(detail.clone()),
            BindError::Sim(SimError::ZeroSampleRate) => ConfigurationError::new_err(detail.clone()),
            BindError::Sim(SimError::Scenario(_)) | BindError::Scenario(_) => {
                ScenarioFailure::new_err(detail.clone())
            }
            BindError::Phase { .. } => PhaseError::new_err(detail.clone()),
            BindError::Consumed => ConsumedError::new_err(detail.clone()),
            BindError::Busy => BusyError::new_err(detail.clone()),
        };
        let value = err.value(py);
        // Setting attributes on a fresh exception instance cannot fail.
        if value.setattr("kind", kind).is_err() || value.setattr("detail", &detail).is_err() {
            tracing::error!(kind, "could not attach kind/detail to exception");
        }
        tracing::debug!(kind, %detail, "raising sadi_py error");
        err
    }
}

impl From<BindError> for PyErr {
    /// Converts under the GIL; exception class is chosen from the variant.
    fn from(e: BindError) -> PyErr {
        Python::attach(|py| e.into_pyerr(py))
    }
}

/// Registers the exception classes on the module.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let py = m.py();
    m.add("SadiError", py.get_type::<SadiError>())?;
    m.add("ConfigurationError", py.get_type::<ConfigurationError>())?;
    m.add("TransportFailure", py.get_type::<TransportFailure>())?;
    m.add("CommandTimeoutError", py.get_type::<CommandTimeoutError>())?;
    m.add("ReadTimeoutError", py.get_type::<ReadTimeoutError>())?;
    m.add(
        "UnexpectedStateError",
        py.get_type::<UnexpectedStateError>(),
    )?;
    m.add("TapError", py.get_type::<TapError>())?;
    m.add("CodecFailure", py.get_type::<CodecFailure>())?;
    m.add("ScenarioFailure", py.get_type::<ScenarioFailure>())?;
    m.add("PhaseError", py.get_type::<PhaseError>())?;
    m.add("ConsumedError", py.get_type::<ConsumedError>())?;
    m.add("BusyError", py.get_type::<BusyError>())?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    // frob:tests crates/sadi-py/src/errors.rs::BindError.kind
    #[test]
    fn kinds_are_stable() {
        assert_eq!(BindError::Consumed.kind(), "consumed");
        assert_eq!(BindError::Busy.kind(), "busy");
        assert_eq!(
            BindError::Transport(TransportError::Closed).kind(),
            "transport_closed"
        );
        assert_eq!(
            BindError::Session(SessionError::ReadTimeout(std::time::Duration::from_millis(
                5
            )))
            .kind(),
            "read_timeout"
        );
        assert_eq!(
            BindError::Phase {
                expected: "a",
                actual: "b"
            }
            .kind(),
            "phase"
        );
    }
}
