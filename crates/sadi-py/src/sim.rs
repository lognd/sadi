//! Simulator submodule: an empty registered stub that R7B fills in.
// frob:ticket 01M6W7R226VMAMHYPDBQTAS277

use pyo3::prelude::*;
use pyo3::types::PyModule;

/// Registers the empty `sim` submodule.
pub(crate) fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    let sub = PyModule::new(m.py(), "sim")?;
    m.add_submodule(&sub)?;
    Ok(())
}
