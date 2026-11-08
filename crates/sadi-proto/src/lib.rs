//! sadi-proto: SADI MOM wire protocol, transport seam and simulator.
//!
//! The wire protocol is UNVERIFIED until a hardware session
//! (docs/protocol.md section 10); unverified behaviour must sit behind
//! a config switch.
#![forbid(unsafe_code)]
#![deny(clippy::wildcard_enum_match_arm, clippy::must_use_candidate)]

pub mod codec;
pub mod error;
pub mod replay;
#[cfg(feature = "serial")]
pub mod serial;
pub mod session;
pub mod sim;
pub mod transport;
#[cfg(feature = "v3")]
pub mod v3;

pub use error::{ProtoError, TransportError};
pub use transport::Transport;
