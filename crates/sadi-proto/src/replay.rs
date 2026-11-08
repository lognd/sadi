//! Raw capture (append-only, never overwritten) and replay of captured traffic.
//!
//! [`RecordingTransport`] wraps any [`Transport`] and appends every raw RX and
//! TX byte to uniquely named files created with `O_EXCL` semantics.
//! [`ReplayTransport`] feeds a captured RX stream back through the normal
//! [`crate::session::Session`] and decoder so field captures become offline
//! regression tests (docs/device/hwprobe.md).

use std::fs::{File, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::Duration;

use tracing::{debug, error, info, trace, warn};

use crate::error::TransportError;
use crate::transport::Transport;

/// Highest numeric suffix tried when a capture stem is already taken.
const MAX_STEM_SUFFIX: u32 = 9_999;

/// Failures creating or reading capture files.
#[derive(Debug, thiserror::Error)]
#[non_exhaustive]
pub enum CaptureError {
    /// A file could not be created, written or read.
    #[error("capture I/O error on {path}: {source}")]
    Io {
        /// File involved.
        path: PathBuf,
        /// Underlying failure.
        #[source]
        source: std::io::Error,
    },
    /// Every candidate name for the stem already exists; nothing was overwritten.
    #[error("no free capture name for stem {stem:?} in {dir}")]
    NoFreeName {
        /// Directory searched.
        dir: PathBuf,
        /// Requested stem.
        stem: String,
    },
}

/// Direction of captured bytes, selecting the file extension.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Direction {
    /// Device to host.
    Rx,
    /// Host to device.
    Tx,
}

impl Direction {
    /// Returns the file suffix for this direction.
    fn suffix(self) -> &'static str {
        match self {
            Direction::Rx => "bin",
            Direction::Tx => "tx.bin",
        }
    }
}

/// One append-only capture file; opened with `create_new`, so it can never clobber data.
#[derive(Debug)]
#[must_use = "a capture file records nothing unless written to"]
pub struct CaptureFile {
    file: File,
    path: PathBuf,
    bytes: u64,
}

impl CaptureFile {
    /// Creates `path` exclusively (fails if it exists) in append mode.
    fn create_exclusive(path: PathBuf) -> Result<Self, std::io::Error> {
        let file = OpenOptions::new()
            .append(true)
            .create_new(true)
            .open(&path)?;
        info!(path = %path.display(), "capture file created");
        Ok(Self {
            file,
            path,
            bytes: 0,
        })
    }

    /// Appends `bytes` exactly as given.
    pub fn append(&mut self, bytes: &[u8]) -> Result<(), CaptureError> {
        self.file.write_all(bytes).map_err(|source| {
            error!(path = %self.path.display(), error = %source, "capture write failed");
            CaptureError::Io {
                path: self.path.clone(),
                source,
            }
        })?;
        self.bytes += bytes.len() as u64;
        trace!(path = %self.path.display(), n = bytes.len(), total = self.bytes, "captured");
        Ok(())
    }

    /// Forces captured bytes to stable storage.
    pub fn sync(&mut self) -> Result<(), CaptureError> {
        self.file.sync_all().map_err(|source| CaptureError::Io {
            path: self.path.clone(),
            source,
        })?;
        debug!(path = %self.path.display(), bytes = self.bytes, "capture synced");
        Ok(())
    }

    /// Returns the file path.
    #[must_use]
    pub fn path(&self) -> &Path {
        &self.path
    }

    /// Returns how many bytes this handle has appended.
    #[must_use]
    pub fn bytes(&self) -> u64 {
        self.bytes
    }
}

/// The RX and TX capture files of one probe run, sharing a unique stem.
#[derive(Debug)]
#[must_use = "a capture set records nothing until wrapped in a RecordingTransport"]
pub struct CaptureSet {
    rx: CaptureFile,
    tx: CaptureFile,
    stem: String,
}

impl CaptureSet {
    /// Creates `<stem>.bin` and `<stem>.tx.bin` in `dir`, adding `-N` to the stem on collision.
    pub fn create_new(dir: &Path, stem: &str) -> Result<Self, CaptureError> {
        std::fs::create_dir_all(dir).map_err(|source| CaptureError::Io {
            path: dir.to_path_buf(),
            source,
        })?;
        for n in 0..=MAX_STEM_SUFFIX {
            let candidate = if n == 0 {
                stem.to_owned()
            } else {
                format!("{stem}-{n}")
            };
            let rx_path = dir.join(format!("{candidate}.{}", Direction::Rx.suffix()));
            let tx_path = dir.join(format!("{candidate}.{}", Direction::Tx.suffix()));
            if rx_path.exists() || tx_path.exists() {
                debug!(candidate = %candidate, "capture stem taken; trying next");
                continue;
            }
            match CaptureFile::create_exclusive(rx_path.clone()) {
                Ok(rx) => match CaptureFile::create_exclusive(tx_path.clone()) {
                    Ok(tx) => {
                        return Ok(Self {
                            rx,
                            tx,
                            stem: candidate,
                        })
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                        warn!(path = %tx_path.display(), "tx capture raced; trying next stem");
                    }
                    Err(source) => {
                        return Err(CaptureError::Io {
                            path: tx_path,
                            source,
                        })
                    }
                },
                Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => {
                    warn!(path = %rx_path.display(), "rx capture raced; trying next stem");
                }
                Err(source) => {
                    return Err(CaptureError::Io {
                        path: rx_path,
                        source,
                    })
                }
            }
        }
        error!(dir = %dir.display(), stem, "no free capture name");
        Err(CaptureError::NoFreeName {
            dir: dir.to_path_buf(),
            stem: stem.to_owned(),
        })
    }

    /// Returns the unique stem actually used (shared by the report file).
    #[must_use]
    pub fn stem(&self) -> &str {
        &self.stem
    }

    /// Returns the RX (`.bin`) file path.
    #[must_use]
    pub fn rx_path(&self) -> &Path {
        self.rx.path()
    }

    /// Returns the TX (`.tx.bin`) file path.
    #[must_use]
    pub fn tx_path(&self) -> &Path {
        self.tx.path()
    }

    /// Returns the (rx, tx) byte counts captured so far.
    #[must_use]
    pub fn byte_counts(&self) -> (u64, u64) {
        (self.rx.bytes(), self.tx.bytes())
    }

    /// Syncs both files to stable storage.
    pub fn sync(&mut self) -> Result<(), CaptureError> {
        self.rx.sync()?;
        self.tx.sync()
    }
}

/// Converts a capture failure into the transport error a failed tap must raise.
fn io_error(e: CaptureError) -> TransportError {
    TransportError::Io(std::io::Error::other(e.to_string()))
}

/// Wraps a transport and records every raw byte before the caller or device sees it.
///
/// A capture write failure fails the call, so nothing is ever sent or consumed
/// unrecorded (TX bytes are recorded before they are written).
#[must_use = "dropping the recorder discards the wrapped transport"]
pub struct RecordingTransport<T: Transport> {
    inner: T,
    captures: CaptureSet,
}

impl<T: Transport> RecordingTransport<T> {
    /// Wraps `inner`, recording into `captures`.
    pub fn new(inner: T, captures: CaptureSet) -> Self {
        info!(
            inner = %inner.description(),
            rx = %captures.rx_path().display(),
            "recording transport created"
        );
        Self { inner, captures }
    }

    /// Returns the capture set (paths and byte counts).
    #[must_use]
    pub fn captures(&self) -> &CaptureSet {
        &self.captures
    }

    /// Syncs the captures and returns the wrapped transport and the capture set.
    pub fn finish(mut self) -> Result<(T, CaptureSet), CaptureError> {
        self.captures.sync()?;
        info!("recording transport finished");
        Ok((self.inner, self.captures))
    }
}

impl<T: Transport> Transport for RecordingTransport<T> {
    /// Records the bytes to the TX file, then writes them to the device.
    fn write_all(&mut self, data: &[u8]) -> Result<(), TransportError> {
        self.captures.tx.append(data).map_err(io_error)?;
        self.inner.write_all(data)
    }

    /// Reads from the device and appends exactly the bytes read to the RX file.
    fn read(&mut self, buf: &mut [u8], timeout: Duration) -> Result<usize, TransportError> {
        let n = self.inner.read(buf, timeout)?;
        if let Some(got) = buf.get(..n) {
            self.captures.rx.append(got).map_err(io_error)?;
        }
        Ok(n)
    }

    /// Purges the wrapped transport (captured bytes are never discarded).
    fn purge(&mut self) -> Result<(), TransportError> {
        debug!("recording transport purge");
        self.inner.purge()
    }

    /// Syncs the captures and closes the wrapped transport.
    fn close(&mut self) -> Result<(), TransportError> {
        self.captures.sync().map_err(io_error)?;
        self.inner.close()
    }

    /// Describes the wrapped transport and the capture stem.
    fn description(&self) -> String {
        format!(
            "{} [recording {}]",
            self.inner.description(),
            self.captures.stem()
        )
    }
}

/// Default bytes handed out per `read` when replaying.
pub const DEFAULT_REPLAY_CHUNK: usize = 612;

/// Transport that serves a captured RX byte stream and swallows all writes.
///
/// Writes are counted and ignored; `purge` is a no-op so the handshake does not
/// discard the capture. When the capture is exhausted `read` returns `Closed`.
#[derive(Debug)]
#[must_use = "a replay transport does nothing until a session reads it"]
pub struct ReplayTransport {
    name: String,
    data: Vec<u8>,
    pos: usize,
    chunk: usize,
    written: usize,
    closed: bool,
}

impl ReplayTransport {
    /// Replays `data`, described as `name`.
    pub fn from_bytes(name: impl Into<String>, data: Vec<u8>) -> Self {
        let name = name.into();
        info!(name = %name, bytes = data.len(), "replay transport created");
        Self {
            name,
            data,
            pos: 0,
            chunk: DEFAULT_REPLAY_CHUNK,
            written: 0,
            closed: false,
        }
    }

    /// Loads a `.bin` RX capture from disk.
    pub fn open(path: &Path) -> Result<Self, CaptureError> {
        let data = std::fs::read(path).map_err(|source| {
            error!(path = %path.display(), error = %source, "cannot read capture");
            CaptureError::Io {
                path: path.to_path_buf(),
                source,
            }
        })?;
        Ok(Self::from_bytes(path.display().to_string(), data))
    }

    /// Limits each read to `chunk` bytes (minimum 1) to exercise decoder reassembly.
    pub fn with_chunk(mut self, chunk: usize) -> Self {
        self.chunk = chunk.max(1);
        self
    }

    /// Returns how many captured bytes have not been read yet.
    #[must_use]
    pub fn remaining(&self) -> usize {
        self.data.len() - self.pos
    }

    /// Returns how many bytes the session wrote (and the replay ignored).
    #[must_use]
    pub fn bytes_written(&self) -> usize {
        self.written
    }
}

impl Transport for ReplayTransport {
    /// Counts and ignores the bytes; the capture is not interactive.
    fn write_all(&mut self, data: &[u8]) -> Result<(), TransportError> {
        if self.closed {
            return Err(TransportError::Closed);
        }
        self.written += data.len();
        trace!(n = data.len(), "replay: write ignored");
        Ok(())
    }

    /// Copies the next chunk of the capture; `Closed` once it is exhausted.
    fn read(&mut self, buf: &mut [u8], _timeout: Duration) -> Result<usize, TransportError> {
        if self.closed || self.pos >= self.data.len() {
            debug!(name = %self.name, "replay exhausted");
            return Err(TransportError::Closed);
        }
        let n = buf.len().min(self.chunk).min(self.remaining());
        buf[..n].copy_from_slice(&self.data[self.pos..self.pos + n]);
        self.pos += n;
        trace!(n, remaining = self.remaining(), "replay read");
        Ok(n)
    }

    /// No-op: the capture must survive the handshake purge.
    fn purge(&mut self) -> Result<(), TransportError> {
        debug!("replay: purge ignored");
        Ok(())
    }

    /// Marks the replay closed.
    fn close(&mut self) -> Result<(), TransportError> {
        self.closed = true;
        Ok(())
    }

    /// Names the replayed capture.
    fn description(&self) -> String {
        format!("replay:{} ({} bytes)", self.name, self.data.len())
    }
}
