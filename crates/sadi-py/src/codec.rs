//! Stateless codec helpers: command encoding, frame decoding, ADC conversion.
// frob:ticket 01M6W7R226VMAMHYPDBQTAS277

use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sadi_proto::codec::{convert, AdcMode, AdcRange, Command, Packet};
use sadi_proto::session::CommandKind;

use crate::convert::{
    Block, BlockData, PacketKind, PyAdcMode, PyAdcRange, PyCommandKind, PyDeviceState,
};
use crate::errors::BindError;
use sadi_proto::session::BlockStats;

/// Converts four Python ranges into the Rust array.
fn four_ranges(v: Option<Vec<PyAdcRange>>) -> Result<[AdcRange; 4], BindError> {
    match v {
        None => Ok([AdcRange::default(); 4]),
        Some(v) => {
            let n = v.len();
            let four: [PyAdcRange; 4] = v
                .try_into()
                .map_err(|_| BindError::Config(format!("ranges needs 4 entries, got {n}")))?;
            Ok(four.map(AdcRange::from))
        }
    }
}

/// Encodes one host command frame; `ranges` only matters for START.
#[pyfunction]
#[pyo3(signature = (kind, ranges=None))]
pub fn encode_command<'py>(
    py: Python<'py>,
    kind: PyCommandKind,
    ranges: Option<Vec<PyAdcRange>>,
) -> Result<Bound<'py, PyBytes>, BindError> {
    let cmd = match CommandKind::from(kind) {
        CommandKind::Query => Command::Query,
        CommandKind::Reset => Command::Reset,
        CommandKind::Stop => Command::Stop,
        CommandKind::Start => Command::Start {
            ranges: four_ranges(ranges)?,
        },
    };
    Ok(PyBytes::new(py, &cmd.encode()))
}

/// What a decoded device frame is, without its sample payload.
#[pyclass(frozen, module = "sadi_py", name = "PacketInfo")]
pub struct PacketInfo {
    /// Packet type.
    #[pyo3(get)]
    kind: PacketKind,
    /// Device state carried by the packet.
    #[pyo3(get)]
    state: PyDeviceState,
    /// Raw device state byte.
    #[pyo3(get)]
    state_byte: u8,
}

#[pymethods]
impl PacketInfo {
    /// Short summary for debugging.
    fn __repr__(&self) -> String {
        format!("PacketInfo(state_byte={})", self.state_byte)
    }
}

/// Decodes exactly one 612-byte device frame into its kind and state.
#[pyfunction]
pub fn decode_packet(frame: &[u8]) -> Result<PacketInfo, BindError> {
    let p = Packet::parse(frame)?;
    let kind = match &p {
        Packet::Version(_) => PacketKind::Version,
        Packet::Data(_) => PacketKind::Data,
        Packet::StopAck(_) => PacketKind::StopAck,
    };
    let st = p.state();
    Ok(PacketInfo {
        kind,
        state: st.into(),
        state_byte: st.to_byte(),
    })
}

/// Decodes one data frame into a one-packet `Block` (`raw` is the frame).
#[pyfunction]
#[pyo3(signature = (frame, adc_mode, ranges=None))]
pub fn decode_data_packet(
    py: Python<'_>,
    frame: &[u8],
    adc_mode: PyAdcMode,
    ranges: Option<Vec<PyAdcRange>>,
) -> PyResult<Block> {
    let ranges = four_ranges(ranges)?;
    let Packet::Data(d) = Packet::parse(frame).map_err(BindError::from)? else {
        return Err(BindError::Config("frame is not a data packet".into()).into());
    };
    let state = d.state;
    BlockData::new(
        std::slice::from_ref(&*d),
        &ranges,
        AdcMode::from(adc_mode),
        BlockStats::default(),
        Some(state),
        frame.to_vec(),
    )
    .into_py(py)
}

/// Converts one raw 14-bit ADC word to volts.
#[pyfunction]
pub fn adc_to_volts(raw: u16, range: PyAdcRange, adc_mode: PyAdcMode) -> f64 {
    convert(range.into(), raw, adc_mode.into())
}
