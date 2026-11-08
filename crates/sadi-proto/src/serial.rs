//! serialport backend over the FTDI VCP (feature `serial`).
//!
//! Unverified wire behaviour (docs/protocol.md section 10): baud is a config
//! value only (FIFO mode ignores it) and RX overflow is detected by a
//! configurable pending-byte limit, not by a device signal.
#![deny(clippy::wildcard_enum_match_arm)]

use std::fmt;
use std::io::{self, Read, Write};
use std::time::Duration;

use serialport::{ClearBuffer, SerialPort, SerialPortType};
use tracing::{debug, error, info, trace, warn};

use crate::error::TransportError;
use crate::transport::Transport;

/// A USB vendor/product id pair.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct UsbId {
    vid: u16,
    pid: u16,
}

impl UsbId {
    /// Build a vendor/product id pair.
    #[must_use]
    pub const fn new(vid: u16, pid: u16) -> Self {
        Self { vid, pid }
    }
    /// USB vendor id.
    #[must_use]
    pub const fn vid(self) -> u16 {
        self.vid
    }
    /// USB product id.
    #[must_use]
    pub const fn pid(self) -> u16 {
        self.pid
    }
}

impl fmt::Display for UsbId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:04x}:{:04x}", self.vid, self.pid)
    }
}

/// Default FTDI allow-list: FT2232H (6010), FT4232H (6014 per ticket), FT232R (6001).
pub const FTDI_ALLOW_LIST: [UsbId; 3] = [
    UsbId::new(0x0403, 0x6010),
    UsbId::new(0x0403, 0x6014),
    UsbId::new(0x0403, 0x6001),
];

/// Invalid [`SerialConfig`] input, rejected at construction.
#[derive(Debug, Clone, PartialEq, Eq, thiserror::Error)]
pub enum SerialConfigError {
    /// The port name was empty.
    #[error("port name must not be empty")]
    EmptyPortName,
    /// The baud rate was zero.
    #[error("baud rate must be nonzero")]
    ZeroBaud,
    /// The I/O timeout was zero.
    #[error("timeout must be nonzero")]
    ZeroTimeout,
    /// The RX limit was zero.
    #[error("rx limit must be nonzero")]
    ZeroRxLimit,
    /// The VID/PID allow-list was empty.
    #[error("allow-list must not be empty")]
    EmptyAllowList,
}

/// Baud rate in bits per second; ignored by the FTDI in FIFO mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct BaudRate(u32);

impl BaudRate {
    /// Documented default (FT2232H maximum); has no effect in FIFO mode.
    pub const DEFAULT: Self = Self(12_000_000);
    /// Build a nonzero baud rate.
    pub fn new(bps: u32) -> Result<Self, SerialConfigError> {
        if bps == 0 {
            return Err(SerialConfigError::ZeroBaud);
        }
        Ok(Self(bps))
    }
    /// The rate in bits per second.
    #[must_use]
    pub const fn get(self) -> u32 {
        self.0
    }
}

/// Default operation timeout applied to the port at open.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IoTimeout(Duration);

impl IoTimeout {
    /// Documented default: 100 ms.
    pub const DEFAULT: Self = Self(Duration::from_millis(100));
    /// Build a nonzero timeout.
    pub fn new(d: Duration) -> Result<Self, SerialConfigError> {
        if d.is_zero() {
            return Err(SerialConfigError::ZeroTimeout);
        }
        Ok(Self(d))
    }
    /// The timeout duration.
    #[must_use]
    pub const fn get(self) -> Duration {
        self.0
    }
}

/// Maximum unread bytes tolerated in the driver before reads report overflow.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct RxLimit(usize);

impl RxLimit {
    /// Documented default: 1 MiB, about 1.7 s of stream at 612 kB/s.
    pub const DEFAULT: Self = Self(1 << 20);
    /// Build a nonzero limit.
    pub fn new(bytes: usize) -> Result<Self, SerialConfigError> {
        if bytes == 0 {
            return Err(SerialConfigError::ZeroRxLimit);
        }
        Ok(Self(bytes))
    }
    /// The limit in bytes.
    #[must_use]
    pub const fn get(self) -> usize {
        self.0
    }
}

/// Validated configuration for opening a [`SerialTransport`].
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct SerialConfig {
    port_name: String,
    baud: BaudRate,
    timeout: IoTimeout,
    rx_limit: RxLimit,
    allow_list: Vec<UsbId>,
}

impl SerialConfig {
    /// Build a config with default baud, timeout, RX limit and FTDI allow-list.
    pub fn new(port_name: impl Into<String>) -> Result<Self, SerialConfigError> {
        let port_name = port_name.into();
        if port_name.is_empty() {
            warn!("serial config rejected: empty port name");
            return Err(SerialConfigError::EmptyPortName);
        }
        Ok(Self {
            port_name,
            baud: BaudRate::DEFAULT,
            timeout: IoTimeout::DEFAULT,
            rx_limit: RxLimit::DEFAULT,
            allow_list: FTDI_ALLOW_LIST.to_vec(),
        })
    }
    /// Replace the baud rate.
    #[must_use]
    pub fn with_baud(mut self, baud: BaudRate) -> Self {
        self.baud = baud;
        self
    }
    /// Replace the default I/O timeout.
    #[must_use]
    pub fn with_timeout(mut self, timeout: IoTimeout) -> Self {
        self.timeout = timeout;
        self
    }
    /// Replace the RX overflow limit.
    #[must_use]
    pub fn with_rx_limit(mut self, rx_limit: RxLimit) -> Self {
        self.rx_limit = rx_limit;
        self
    }
    /// Replace the VID/PID allow-list; must be nonempty.
    pub fn with_allow_list(mut self, ids: Vec<UsbId>) -> Result<Self, SerialConfigError> {
        if ids.is_empty() {
            warn!("serial config rejected: empty allow-list");
            return Err(SerialConfigError::EmptyAllowList);
        }
        self.allow_list = ids;
        Ok(self)
    }
    /// Port name or path to open.
    #[must_use]
    pub fn port_name(&self) -> &str {
        &self.port_name
    }
    /// Configured baud rate.
    #[must_use]
    pub fn baud(&self) -> BaudRate {
        self.baud
    }
    /// Configured I/O timeout.
    #[must_use]
    pub fn timeout(&self) -> IoTimeout {
        self.timeout
    }
    /// Configured RX overflow limit.
    #[must_use]
    pub fn rx_limit(&self) -> RxLimit {
        self.rx_limit
    }
    /// VID/PID allow-list used by [`list_ports`].
    #[must_use]
    pub fn allow_list(&self) -> &[UsbId] {
        &self.allow_list
    }
}

/// A discovered serial port whose USB ids passed the allow-list.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PortCandidate {
    name: String,
    id: UsbId,
    product: Option<String>,
}

impl PortCandidate {
    /// OS port name or path.
    #[must_use]
    pub fn name(&self) -> &str {
        &self.name
    }
    /// USB vendor/product id.
    #[must_use]
    pub fn id(&self) -> UsbId {
        self.id
    }
    /// USB product string, if reported (e.g. "SADI 2.0 A").
    #[must_use]
    pub fn product(&self) -> Option<&str> {
        self.product.as_deref()
    }
}

/// Map a serialport error into the transport error space.
fn map_port_error(e: serialport::Error) -> TransportError {
    if matches!(e.kind, serialport::ErrorKind::NoDevice) {
        error!(error = %e, "serial device disappeared");
        return TransportError::Closed;
    }
    error!(error = %e, "serial port error");
    TransportError::Io(io::Error::from(e))
}

/// Map an I/O error from read/write into the transport error space.
fn map_io_error(e: io::Error, timeout: Duration) -> TransportError {
    let kind = e.kind();
    if kind == io::ErrorKind::TimedOut || kind == io::ErrorKind::WouldBlock {
        trace!(?timeout, "serial op timed out");
        TransportError::Timeout(timeout)
    } else if kind == io::ErrorKind::BrokenPipe || kind == io::ErrorKind::NotConnected {
        error!(error = %e, "serial device closed under us");
        TransportError::Closed
    } else {
        error!(error = %e, "serial I/O error");
        TransportError::Io(e)
    }
}

/// List ports whose USB ids are on `allow_list`, in OS enumeration order.
///
/// On Linux, enumeration details need the `udev` feature (libudev).
pub fn list_ports(allow_list: &[UsbId]) -> Result<Vec<PortCandidate>, TransportError> {
    let all = serialport::available_ports().map_err(map_port_error)?;
    debug!(total = all.len(), "enumerated serial ports");
    let mut out = Vec::new();
    for info in all {
        match info.port_type {
            SerialPortType::UsbPort(u) => {
                let id = UsbId::new(u.vid, u.pid);
                if allow_list.contains(&id) {
                    info!(port = %info.port_name, %id, "port accepted");
                    out.push(PortCandidate {
                        name: info.port_name,
                        id,
                        product: u.product,
                    });
                } else {
                    debug!(port = %info.port_name, %id, "port skipped: not on allow-list");
                }
            }
            SerialPortType::PciPort | SerialPortType::BluetoothPort | SerialPortType::Unknown => {
                debug!(port = %info.port_name, "port skipped: not USB");
            }
        }
    }
    Ok(out)
}

/// Move-only serial handle implementing [`Transport`] over a serialport.
///
/// Semantics: `purge` clears the OS driver buffers in both directions (bytes
/// still in the device FIFO may arrive afterwards); `close` (trait) releases
/// the port and later calls fail with `Closed`; [`SerialTransport::shutdown`]
/// consumes the handle. If unread bytes exceed the RX limit, `read` returns
/// `Overflow` without consuming data; `purge` recovers.
#[must_use = "dropping the handle closes the port"]
pub struct SerialTransport {
    port: Option<Box<dyn SerialPort>>,
    name: String,
    rx_limit: RxLimit,
}

impl SerialTransport {
    /// Open the configured port with the configured baud and timeout.
    pub fn open(cfg: &SerialConfig) -> Result<Self, TransportError> {
        info!(
            port = cfg.port_name(),
            baud = cfg.baud().get(),
            "opening serial port"
        );
        let port = serialport::new(cfg.port_name(), cfg.baud().get())
            .timeout(cfg.timeout().get())
            .open()
            .map_err(map_port_error)?;
        Ok(Self::from_port(
            port,
            cfg.port_name().to_owned(),
            cfg.rx_limit(),
        ))
    }

    /// Wrap an already-open port (used for pty loopback and alternate openers).
    pub fn from_port(port: Box<dyn SerialPort>, name: String, rx_limit: RxLimit) -> Self {
        debug!(port = %name, "serial transport created from open port");
        Self {
            port: Some(port),
            name,
            rx_limit,
        }
    }

    /// Close the port, consuming the handle.
    pub fn shutdown(mut self) -> Result<(), TransportError> {
        info!(port = %self.name, "shutdown: consuming serial handle");
        self.close_inner()
    }

    fn port_mut(&mut self) -> Result<&mut Box<dyn SerialPort>, TransportError> {
        match self.port.as_mut() {
            Some(p) => Ok(p),
            None => {
                warn!(port = %self.name, "operation on closed serial transport");
                Err(TransportError::Closed)
            }
        }
    }

    fn close_inner(&mut self) -> Result<(), TransportError> {
        match self.port.take() {
            Some(p) => {
                drop(p);
                info!(port = %self.name, "serial port closed");
                Ok(())
            }
            None => {
                warn!(port = %self.name, "close on already-closed serial transport");
                Err(TransportError::Closed)
            }
        }
    }
}

impl fmt::Debug for SerialTransport {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.debug_struct("SerialTransport")
            .field("name", &self.name)
            .field("open", &self.port.is_some())
            .finish()
    }
}

impl Drop for SerialTransport {
    fn drop(&mut self) {
        if self.port.is_some() {
            debug!(port = %self.name, "serial transport dropped while open");
        }
    }
}

impl Transport for SerialTransport {
    fn write_all(&mut self, data: &[u8]) -> Result<(), TransportError> {
        let port = self.port_mut()?;
        trace!(len = data.len(), "serial write");
        port.write_all(data)
            .and_then(|()| port.flush())
            .map_err(|e| map_io_error(e, Duration::ZERO))
    }

    fn read(&mut self, buf: &mut [u8], timeout: Duration) -> Result<usize, TransportError> {
        let limit = self.rx_limit.get();
        let name = self.name.clone();
        let port = self.port_mut()?;
        let pending = port.bytes_to_read().map_err(map_port_error)? as usize;
        if pending > limit {
            error!(port = %name, pending, limit, "rx overflow");
            return Err(TransportError::Overflow { pending, limit });
        }
        port.set_timeout(timeout).map_err(map_port_error)?;
        match port.read(buf) {
            Ok(0) if !buf.is_empty() => {
                warn!(port = %name, "read returned EOF; treating as closed");
                Err(TransportError::Closed)
            }
            Ok(n) => {
                trace!(n, "serial read");
                Ok(n)
            }
            Err(e) => Err(map_io_error(e, timeout)),
        }
    }

    fn purge(&mut self) -> Result<(), TransportError> {
        let name = self.name.clone();
        let port = self.port_mut()?;
        port.clear(ClearBuffer::All).map_err(map_port_error)?;
        info!(port = %name, "serial buffers purged");
        Ok(())
    }

    fn close(&mut self) -> Result<(), TransportError> {
        self.close_inner()
    }

    fn description(&self) -> String {
        format!("serial:{}", self.name)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // frob:tests crates/sadi-proto/src/serial.rs::SerialConfig.new
    #[test]
    fn config_rejects_empty_name() {
        assert_eq!(SerialConfig::new(""), Err(SerialConfigError::EmptyPortName));
        let c = SerialConfig::new("/dev/ttyUSB0").unwrap();
        assert_eq!(c.allow_list(), &FTDI_ALLOW_LIST);
        assert_eq!(c.baud(), BaudRate::DEFAULT);
    }

    // frob:tests crates/sadi-proto/src/serial.rs::SerialConfig.with_allow_list
    #[test]
    fn config_rejects_empty_allow_list() {
        let c = SerialConfig::new("p").unwrap();
        assert_eq!(
            c.with_allow_list(vec![]),
            Err(SerialConfigError::EmptyAllowList)
        );
    }

    // frob:tests crates/sadi-proto/src/serial.rs::BaudRate.new
    // frob:tests crates/sadi-proto/src/serial.rs::IoTimeout.new
    // frob:tests crates/sadi-proto/src/serial.rs::RxLimit.new
    #[test]
    fn newtypes_reject_zero() {
        assert_eq!(BaudRate::new(0), Err(SerialConfigError::ZeroBaud));
        assert_eq!(
            IoTimeout::new(Duration::ZERO),
            Err(SerialConfigError::ZeroTimeout)
        );
        assert_eq!(RxLimit::new(0), Err(SerialConfigError::ZeroRxLimit));
        assert_eq!(BaudRate::new(9600).unwrap().get(), 9600);
    }

    // frob:tests crates/sadi-proto/src/serial.rs::SerialConfig.with_baud
    // frob:tests crates/sadi-proto/src/serial.rs::SerialConfig.with_timeout
    // frob:tests crates/sadi-proto/src/serial.rs::SerialConfig.with_rx_limit
    // frob:tests crates/sadi-proto/src/serial.rs::RxLimit.get
    // frob:tests crates/sadi-proto/src/serial.rs::UsbId.vid
    // frob:tests crates/sadi-proto/src/serial.rs::UsbId.pid
    #[test]
    fn builders_replace_values() {
        let c = SerialConfig::new("p")
            .unwrap()
            .with_baud(BaudRate::new(115_200).unwrap())
            .with_timeout(IoTimeout::new(Duration::from_secs(1)).unwrap())
            .with_rx_limit(RxLimit::new(8).unwrap());
        assert_eq!(c.baud().get(), 115_200);
        assert_eq!(c.timeout().get(), Duration::from_secs(1));
        assert_eq!(c.rx_limit().get(), 8);
        let id = c.allow_list()[0];
        assert_eq!((id.vid(), id.pid()), (0x0403, 0x6010));
    }

    // frob:tests crates/sadi-proto/src/serial.rs::PortCandidate.id
    // frob:tests crates/sadi-proto/src/serial.rs::PortCandidate.product
    // frob:tests crates/sadi-proto/src/serial.rs::PortCandidate.name
    #[test]
    fn candidate_accessors() {
        let p = PortCandidate {
            name: "n".into(),
            id: UsbId::new(1, 2),
            product: Some("SADI 2.0 A".into()),
        };
        assert_eq!(
            (p.name(), p.id(), p.product()),
            ("n", UsbId::new(1, 2), Some("SADI 2.0 A"))
        );
    }

    #[test]
    fn usb_id_display_is_hex() {
        assert_eq!(UsbId::new(0x0403, 0x6010).to_string(), "0403:6010");
    }
}
