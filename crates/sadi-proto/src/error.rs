//! Error enums for the protocol and transport layers.

use std::time::Duration;

/// Failures raised by a [`crate::Transport`] backend.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum TransportError {
    /// A read produced no data within the allowed time.
    #[error("transport timed out after {0:?}")]
    Timeout(Duration),
    /// The transport was closed or the device disappeared.
    #[error("transport closed")]
    Closed,
    /// Unread input exceeded the configured RX limit; purge to recover.
    #[error("receive overflow: {pending} bytes pending exceeds limit {limit}")]
    Overflow {
        /// Bytes waiting in the driver buffer when the check ran.
        pending: usize,
        /// Configured maximum of pending bytes.
        limit: usize,
    },
    /// Underlying OS or driver I/O failure.
    #[error("transport I/O error: {0}")]
    Io(#[from] std::io::Error),
}

/// Failures raised while encoding, decoding or driving the protocol.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum ProtoError {
    /// The underlying transport failed.
    #[error("transport error: {0}")]
    Transport(#[from] TransportError),
    /// Received bytes did not form a valid packet.
    #[error("malformed packet: {0}")]
    Malformed(String),
    /// The device answered in a way the state machine did not expect.
    #[error("unexpected response: {0}")]
    Unexpected(String),
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn transport_error_converts_into_proto_error() {
        let e: ProtoError = TransportError::Closed.into();
        assert_eq!(e.to_string(), "transport error: transport closed");
    }

    #[test]
    fn overflow_message_mentions_counts() {
        let e = TransportError::Overflow {
            pending: 9,
            limit: 4,
        };
        assert_eq!(
            e.to_string(),
            "receive overflow: 9 bytes pending exceeds limit 4"
        );
    }

    #[test]
    fn timeout_message_mentions_duration() {
        let e = TransportError::Timeout(Duration::from_millis(5));
        assert!(e.to_string().contains("5ms"));
    }
}
