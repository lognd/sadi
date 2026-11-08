//! Build metadata and the built-in self-test: `__version__`, `PROTOCOL_VERSION`,
//! `serial_features()` and `selftest()` (read by doctor checks EXT-020/040/050).
// frob:ticket 01M6WN9FATNMDVP10GGDEC40NP

use pyo3::prelude::*;
use sadi_proto::codec::{AdcRange, Command};
use sadi_proto::sim::scenario::Scenario;

use crate::errors::BindError;

/// Host/device wire-protocol revision this build speaks.
pub const PROTOCOL_VERSION: u32 = 1;

/// Name of the builtin scenario the self-test must be able to load.
const SELFTEST_SCENARIO: &str = "clean";

/// Optional sadi-proto capabilities compiled into this build.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SerialFeature {
    /// Real serial-port backend.
    Serial,
    /// Linux port enumeration via libudev.
    Udev,
}

impl SerialFeature {
    /// Every feature, in reporting order (extend together with the match below).
    const ALL: [SerialFeature; 2] = [SerialFeature::Serial, SerialFeature::Udev];

    /// Stable name reported to Python.
    fn name(self) -> &'static str {
        match self {
            SerialFeature::Serial => "serial",
            SerialFeature::Udev => "udev",
        }
    }

    /// Whether this build was compiled with the feature.
    fn enabled(self) -> bool {
        match self {
            SerialFeature::Serial => cfg!(feature = "serial"),
            SerialFeature::Udev => cfg!(feature = "udev"),
        }
    }
}

/// Names of the serial features compiled into this build.
fn enabled_features() -> Vec<&'static str> {
    SerialFeature::ALL
        .into_iter()
        .filter(|f| f.enabled())
        .map(SerialFeature::name)
        .collect()
}

/// Round-trips every command through the codec and loads the builtin scenario.
fn run_selftest() -> Result<(), BindError> {
    let commands = [
        Command::Start {
            ranges: [AdcRange::default(); 4],
        },
        Command::Stop,
        Command::Reset,
        Command::Query,
    ];
    for cmd in commands {
        let back = Command::decode(&cmd.encode())?;
        if back != cmd {
            tracing::error!(?cmd, ?back, "command round-trip mismatch");
            return Err(BindError::SelfTest(format!(
                "command {cmd:?} decoded as {back:?}"
            )));
        }
    }
    Scenario::builtin(SELFTEST_SCENARIO)?;
    tracing::info!("selftest passed");
    Ok(())
}

/// Lists the serial features compiled into this build (for example `udev`).
#[pyfunction]
pub fn serial_features() -> Vec<&'static str> {
    enabled_features()
}

/// Runs the codec and scenario self-test; raises on any disagreement.
#[pyfunction]
pub fn selftest() -> Result<(), BindError> {
    run_selftest()
}

/// Registers the metadata attributes and functions on the module.
pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("PROTOCOL_VERSION", PROTOCOL_VERSION)?;
    m.add_function(wrap_pyfunction!(serial_features, m)?)?;
    m.add_function(wrap_pyfunction!(selftest, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    // frob:tests crates/sadi-py/src/meta.rs::run_selftest
    // frob:tests crates/sadi-py/src/meta.rs::selftest
    #[test]
    fn selftest_passes() {
        assert!(run_selftest().is_ok());
        assert!(selftest().is_ok());
    }

    // frob:tests crates/sadi-py/src/meta.rs::enabled_features
    // frob:tests crates/sadi-py/src/meta.rs::serial_features
    #[test]
    fn features_match_cfg() {
        let got = enabled_features();
        assert_eq!(got, serial_features());
        assert_eq!(got.contains(&"serial"), cfg!(feature = "serial"));
        assert_eq!(got.contains(&"udev"), cfg!(feature = "udev"));
    }
}
