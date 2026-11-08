//! Placeholder so R8 can add acquisition bindings here without touching `lib.rs`.
// frob:ticket 01M6W7R226VMAMHYPDBQTAS277

use pyo3::prelude::*;

/// Registers nothing yet.
#[allow(clippy::unnecessary_wraps)]
pub(crate) fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
