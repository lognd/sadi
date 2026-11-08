//! Python bindings for the SADI device core (module `sadi_py._native`).
// frob:ticket 01M6W7R226VMAMHYPDBQTAS277
#![forbid(unsafe_code)]

mod acq;
mod codec;
mod convert;
mod device;
mod errors;
mod meta;
mod session;
mod sim;

use pyo3::prelude::*;

/// Native module entry point.
#[pymodule]
fn _native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    errors::register(m)?;
    m.add_class::<convert::PyAdcRange>()?;
    m.add_class::<convert::PyAdcMode>()?;
    m.add_class::<convert::PyHandshake>()?;
    m.add_class::<convert::PyIdempotence>()?;
    m.add_class::<convert::PyCommandKind>()?;
    m.add_class::<convert::PyDeviceState>()?;
    m.add_class::<convert::Phase>()?;
    m.add_class::<convert::PacketKind>()?;
    m.add_class::<convert::Block>()?;
    m.add_class::<session::Session>()?;
    m.add_class::<session::VersionInfo>()?;
    m.add_class::<device::SessionConfig>()?;
    m.add_class::<device::PortInfo>()?;
    m.add_class::<codec::PacketInfo>()?;
    m.add_function(wrap_pyfunction!(device::open_serial, m)?)?;
    m.add_function(wrap_pyfunction!(device::open_sim, m)?)?;
    m.add_function(wrap_pyfunction!(device::ports, m)?)?;
    m.add_function(wrap_pyfunction!(codec::encode_command, m)?)?;
    m.add_function(wrap_pyfunction!(codec::decode_packet, m)?)?;
    m.add_function(wrap_pyfunction!(codec::decode_data_packet, m)?)?;
    m.add_function(wrap_pyfunction!(codec::adc_to_volts, m)?)?;
    meta::register(m)?;
    sim::register(m)?;
    acq::register(m)?;
    Ok(())
}
