//! Rust-to-Python value conversion: mirrored enums and numpy-backed blocks.
//!
//! Enums are mirrored one-to-one with exhaustive matches (no wildcard arm), so
//! a new upstream variant is a compile error here rather than a silent
//! fallthrough. Blocks cross the boundary as numpy arrays, never as
//! per-sample Python objects.
// frob:ticket 01M6W7R226VMAMHYPDBQTAS277

use numpy::{PyArray1, PyArray2, PyArrayMethods};
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use sadi_proto::codec::{AdcMode, AdcRange, DataPacket, DeviceState};
use sadi_proto::session::{BlockStats, CommandKind, Handshake, Idempotence};

/// Declares a Python enum mirroring a C-like Rust enum, with total `From` both ways.
macro_rules! mirror_enum {
    ($(#[$m:meta])* $py:ident($pyname:literal) <=> $rs:ty {
        $($v:ident : $pyv:literal <=> $rv:path),+ $(,)?
    }) => {
        $(#[$m])*
        #[pyclass(eq, eq_int, frozen, hash, from_py_object, module = "sadi_py", name = $pyname)]
        #[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
        pub enum $py {
            $( #[pyo3(name = $pyv)] $v ),+
        }

        impl From<$py> for $rs {
            /// Total mapping from the Python-facing enum.
            fn from(v: $py) -> $rs {
                match v { $( $py::$v => $rv ),+ }
            }
        }

        impl From<$rs> for $py {
            /// Total mapping to the Python-facing enum.
            fn from(v: $rs) -> $py {
                match v { $( $rv => $py::$v ),+ }
            }
        }
    };
}

mirror_enum! {
    /// ADS8688 input range of one channel (Start-time setting).
    PyAdcRange("AdcRange") <=> AdcRange {
        Pm10_24: "PM10_24" <=> AdcRange::Pm10_24,
        Pm5_12: "PM5_12" <=> AdcRange::Pm5_12,
        Pm2_56: "PM2_56" <=> AdcRange::Pm2_56,
        Pm1_28: "PM1_28" <=> AdcRange::Pm1_28,
        Pm0_64: "PM0_64" <=> AdcRange::Pm0_64,
        Unipolar10_24: "UNIPOLAR10_24" <=> AdcRange::Unipolar10_24,
        Unipolar5_12: "UNIPOLAR5_12" <=> AdcRange::Unipolar5_12,
        Unipolar2_56: "UNIPOLAR2_56" <=> AdcRange::Unipolar2_56,
        Unipolar1_28: "UNIPOLAR1_28" <=> AdcRange::Unipolar1_28,
    }
}

mirror_enum! {
    /// Raw-code-to-volts formula; always chosen explicitly.
    PyAdcMode("AdcMode") <=> AdcMode {
        DllCompatible: "DLL_COMPATIBLE" <=> AdcMode::DllCompatible,
        Ideal: "IDEAL" <=> AdcMode::Ideal,
    }
}

mirror_enum! {
    /// Which commands `connect` issues after the purge.
    PyHandshake("Handshake") <=> Handshake {
        QueryResetQuery: "QUERY_RESET_QUERY" <=> Handshake::QueryResetQuery,
        QueryOnly: "QUERY_ONLY" <=> Handshake::QueryOnly,
    }
}

mirror_enum! {
    /// Whether Start/Stop are skipped when the device is already in the target state.
    PyIdempotence("Idempotence") <=> Idempotence {
        SkipIfAlready: "SKIP_IF_ALREADY" <=> Idempotence::SkipIfAlready,
        AlwaysSend: "ALWAYS_SEND" <=> Idempotence::AlwaysSend,
    }
}

mirror_enum! {
    /// The four host commands.
    PyCommandKind("CommandKind") <=> CommandKind {
        Query: "QUERY" <=> CommandKind::Query,
        Reset: "RESET" <=> CommandKind::Reset,
        Start: "START" <=> CommandKind::Start,
        Stop: "STOP" <=> CommandKind::Stop,
    }
}

/// Device state byte; `UNKNOWN` carries its raw value in `state_byte` fields.
#[pyclass(
    eq,
    eq_int,
    frozen,
    hash,
    from_py_object,
    module = "sadi_py",
    name = "DeviceState"
)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum PyDeviceState {
    /// Wire value 1: just booted.
    #[pyo3(name = "BOOTED")]
    Booted,
    /// Wire value 2: stopped.
    #[pyo3(name = "STOPPED")]
    Stopped,
    /// Wire value 3: streaming.
    #[pyo3(name = "RUNNING")]
    Running,
    /// Any other wire value.
    #[pyo3(name = "UNKNOWN")]
    Unknown,
}

impl From<DeviceState> for PyDeviceState {
    /// Total mapping; unknown bytes collapse to `UNKNOWN` (the byte is kept separately).
    fn from(s: DeviceState) -> Self {
        match s {
            DeviceState::Booted => PyDeviceState::Booted,
            DeviceState::Stopped => PyDeviceState::Stopped,
            DeviceState::Running => PyDeviceState::Running,
            DeviceState::Unknown(_) => PyDeviceState::Unknown,
        }
    }
}

/// Session phase as seen from Python.
#[pyclass(
    eq,
    eq_int,
    frozen,
    hash,
    from_py_object,
    module = "sadi_py",
    name = "Phase"
)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum Phase {
    /// Transport open, nothing sent.
    #[pyo3(name = "DISCONNECTED")]
    Disconnected,
    /// Handshake done, commands allowed.
    #[pyo3(name = "CONNECTED")]
    Connected,
    /// Device streaming.
    #[pyo3(name = "STREAMING")]
    Streaming,
    /// Stop acknowledged.
    #[pyo3(name = "STOPPED")]
    Stopped,
    /// Handle consumed by `close()`.
    #[pyo3(name = "CLOSED")]
    Closed,
}

impl Phase {
    /// Lowercase name used in error messages.
    #[must_use]
    pub fn as_str(self) -> &'static str {
        match self {
            Phase::Disconnected => "disconnected",
            Phase::Connected => "connected",
            Phase::Streaming => "streaming",
            Phase::Stopped => "stopped",
            Phase::Closed => "closed",
        }
    }
}

/// Kind of a decoded device packet.
#[pyclass(
    eq,
    eq_int,
    frozen,
    hash,
    from_py_object,
    module = "sadi_py",
    name = "PacketKind"
)]
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub enum PacketKind {
    /// Boot or Query reply.
    #[pyo3(name = "VERSION")]
    Version,
    /// Streamed samples.
    #[pyo3(name = "DATA")]
    Data,
    /// Stop acknowledgement.
    #[pyo3(name = "STOP_ACK")]
    StopAck,
}

/// Decoded block contents as plain Rust vectors, built without the GIL.
pub struct BlockData {
    raw: Vec<u8>,
    volts: Vec<f64>,
    adc_raw: Vec<u16>,
    encoder: Vec<i32>,
    msg_count: Vec<u32>,
    digital_inputs: Vec<u8>,
    stats: BlockStats,
    device_state: Option<DeviceState>,
}

impl BlockData {
    /// Flattens `packets` into column vectors, converting ADC words with `ranges`/`mode`.
    #[must_use]
    pub fn new(
        packets: &[DataPacket],
        ranges: &[AdcRange; 4],
        mode: AdcMode,
        stats: BlockStats,
        device_state: Option<DeviceState>,
        raw: Vec<u8>,
    ) -> Self {
        let n = packets.iter().map(|p| p.samples.len()).sum::<usize>();
        let mut d = BlockData {
            raw,
            volts: Vec::with_capacity(n * 4),
            adc_raw: Vec::with_capacity(n * 4),
            encoder: Vec::with_capacity(n),
            msg_count: Vec::with_capacity(packets.len()),
            digital_inputs: Vec::with_capacity(packets.len()),
            stats,
            device_state,
        };
        for p in packets {
            d.msg_count.push(p.msg_count);
            d.digital_inputs.push(p.digital_inputs);
            for s in &p.samples {
                d.encoder.push(s.encoder);
                d.adc_raw.extend_from_slice(&s.adc_raw);
                d.volts.extend_from_slice(&s.volts(ranges, mode));
            }
        }
        tracing::debug!(
            packets = packets.len(),
            samples = d.encoder.len(),
            raw_bytes = d.raw.len(),
            "block flattened"
        );
        d
    }

    /// Number of samples (rows) in the block.
    #[cfg(test)]
    #[must_use]
    pub fn len(&self) -> usize {
        self.encoder.len()
    }

    /// True when the block carries no samples.
    #[cfg(test)]
    #[must_use]
    pub fn is_empty(&self) -> bool {
        self.encoder.is_empty()
    }

    /// Moves the columns into numpy arrays (needs the GIL).
    pub fn into_py(self, py: Python<'_>) -> PyResult<Block> {
        let n = self.encoder.len();
        let state_byte = self.device_state.map(DeviceState::to_byte);
        Ok(Block {
            raw: PyBytes::new(py, &self.raw).unbind(),
            volts: PyArray1::from_vec(py, self.volts).reshape([n, 4])?.unbind(),
            adc_raw: PyArray1::from_vec(py, self.adc_raw)
                .reshape([n, 4])?
                .unbind(),
            encoder: PyArray1::from_vec(py, self.encoder).unbind(),
            msg_count: PyArray1::from_vec(py, self.msg_count).unbind(),
            digital_inputs: PyArray1::from_vec(py, self.digital_inputs).unbind(),
            n_samples: n,
            dropped_bytes: self.stats.dropped_bytes,
            malformed: self.stats.malformed,
            gap_events: self.stats.gap_events,
            missed_packets: self.stats.missed_packets,
            device_state: self.device_state.map(PyDeviceState::from),
            device_state_byte: state_byte,
        })
    }
}

/// One `read_block` result: raw wire bytes plus decoded numpy columns.
#[pyclass(frozen, module = "sadi_py", name = "Block")]
pub struct Block {
    /// Every raw RX byte read since the previous block, exactly as received (for the WAL).
    #[pyo3(get)]
    raw: Py<PyBytes>,
    /// Volts, shape (n_samples, 4), float64.
    #[pyo3(get)]
    volts: Py<PyArray2<f64>>,
    /// Raw ADC words, shape (n_samples, 4), uint16.
    #[pyo3(get)]
    adc_raw: Py<PyArray2<u16>>,
    /// Encoder counts, shape (n_samples,), int32.
    #[pyo3(get)]
    encoder: Py<PyArray1<i32>>,
    /// Per-packet msgCount, shape (n_packets,), uint32.
    #[pyo3(get)]
    msg_count: Py<PyArray1<u32>>,
    /// Per-packet digital input byte, shape (n_packets,), uint8.
    #[pyo3(get)]
    digital_inputs: Py<PyArray1<u8>>,
    /// Number of samples (rows).
    #[pyo3(get)]
    n_samples: usize,
    /// Bytes the decoder dropped while resyncing during this block.
    #[pyo3(get)]
    dropped_bytes: u64,
    /// Framed packets that failed to parse during this block.
    #[pyo3(get)]
    malformed: u64,
    /// msgCount gap events during this block.
    #[pyo3(get)]
    gap_events: u64,
    /// Data packets missing according to msgCount jumps.
    #[pyo3(get)]
    missed_packets: u64,
    /// Device state last seen, if any.
    #[pyo3(get)]
    device_state: Option<PyDeviceState>,
    /// Raw device state byte last seen (distinguishes unknown states).
    #[pyo3(get)]
    device_state_byte: Option<u8>,
}

#[pymethods]
impl Block {
    /// Returns the number of samples.
    fn __len__(&self) -> usize {
        self.n_samples
    }

    /// Short summary for debugging.
    fn __repr__(&self) -> String {
        format!(
            "Block(n_samples={}, dropped_bytes={})",
            self.n_samples, self.dropped_bytes
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use sadi_proto::codec::Sample;

    // frob:tests crates/sadi-py/src/convert.rs::BlockData.new
    #[test]
    fn block_data_flattens_columns() {
        let mut p = DataPacket {
            state: DeviceState::Running,
            digital_inputs: 5,
            msg_count: 9,
            samples: [Sample::default(); 50],
        };
        p.samples[1].encoder = -3;
        p.samples[1].adc_raw = [1, 2, 3, 4];
        let ranges = [AdcRange::Pm5_12; 4];
        let d = BlockData::new(
            &[p],
            &ranges,
            AdcMode::Ideal,
            BlockStats::default(),
            Some(DeviceState::Running),
            vec![1, 2],
        );
        assert_eq!(d.len(), 50);
        assert_eq!(d.volts.len(), 200);
        assert_eq!(d.encoder[1], -3);
        assert_eq!(&d.adc_raw[4..8], &[1, 2, 3, 4]);
        assert_eq!(d.msg_count, vec![9]);
        assert_eq!(d.digital_inputs, vec![5]);
        assert!(!d.is_empty());
    }

    // frob:tests crates/sadi-py/src/convert.rs::PyDeviceState
    #[test]
    fn device_state_mapping_is_total() {
        assert_eq!(
            PyDeviceState::from(DeviceState::Unknown(9)),
            PyDeviceState::Unknown
        );
        assert_eq!(
            PyDeviceState::from(DeviceState::Running),
            PyDeviceState::Running
        );
        assert_eq!(
            AdcRange::from(PyAdcRange::from(AdcRange::Pm0_64)),
            AdcRange::Pm0_64
        );
    }
}
