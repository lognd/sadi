//! The byte-pipe seam between the protocol and a physical or simulated device.

use std::time::Duration;

use crate::error::TransportError;

/// Byte transport to a SADI board; the seam for a future D2XX/libusb backend.
pub trait Transport: Send {
    /// Write the whole buffer to the device.
    fn write_all(&mut self, data: &[u8]) -> Result<(), TransportError>;
    /// Read up to `buf.len()` bytes, waiting at most `timeout`; returns bytes read.
    fn read(&mut self, buf: &mut [u8], timeout: Duration) -> Result<usize, TransportError>;
    /// Discard any pending input and output bytes.
    fn purge(&mut self) -> Result<(), TransportError>;
    /// Close the transport; later calls fail with `TransportError::Closed`.
    fn close(&mut self) -> Result<(), TransportError>;
    /// Human-readable description (port name, simulator, replay file).
    fn description(&self) -> String;
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Null;
    impl Transport for Null {
        fn write_all(&mut self, _: &[u8]) -> Result<(), TransportError> {
            Ok(())
        }
        fn read(&mut self, _: &mut [u8], t: Duration) -> Result<usize, TransportError> {
            Err(TransportError::Timeout(t))
        }
        fn purge(&mut self) -> Result<(), TransportError> {
            Ok(())
        }
        fn close(&mut self) -> Result<(), TransportError> {
            Ok(())
        }
        fn description(&self) -> String {
            "null".into()
        }
    }

    // frob:tests crates/sadi-proto/src/transport.rs::Transport.write_all
    // frob:tests crates/sadi-proto/src/transport.rs::Transport.purge
    // frob:tests crates/sadi-proto/src/transport.rs::Transport.close
    // frob:tests crates/sadi-proto/src/transport.rs::Transport.read
    // frob:tests crates/sadi-proto/src/transport.rs::Transport.description
    #[test]
    fn trait_is_object_safe_and_send() {
        fn assert_send<T: Send + ?Sized>() {}
        assert_send::<dyn Transport>();
        let mut t: Box<dyn Transport> = Box::new(Null);
        let mut b = [0u8; 4];
        assert!(matches!(
            t.read(&mut b, Duration::from_millis(1)),
            Err(TransportError::Timeout(_))
        ));
        assert_eq!(t.description(), "null");
        assert!(t.write_all(b"x").is_ok());
        assert!(t.purge().is_ok());
        assert!(t.close().is_ok());
    }
}
