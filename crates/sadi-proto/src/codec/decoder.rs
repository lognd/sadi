//! Streaming resync decoder for the 612-byte device packet stream.

use super::packet::{Packet, PACKET_LEN};
use super::{CodecError, SYNC, TAIL};

/// Counters describing what the decoder has seen so far.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct DecoderStats {
    /// Packets that framed and parsed successfully.
    pub packets: u64,
    /// Framed packets that failed to parse (for example unknown type).
    pub malformed: u64,
    /// Bytes discarded while searching for a valid frame.
    pub dropped_bytes: u64,
    /// Number of times a data msgCount jumped forward by more than one.
    pub gap_events: u64,
    /// Total data packets missing according to msgCount jumps.
    pub missed_packets: u64,
}

/// Incremental decoder: push bytes in any chunking, pull packets out.
///
/// Framing follows momLab.dll `getPacket`: a packet starts at a 0x55 whose
/// bytes at +608..+611 are AA 55 AA 55; anything else is dropped.
#[derive(Debug, Default)]
pub struct Decoder {
    buf: Vec<u8>,
    stats: DecoderStats,
    last_msg: Option<u32>,
}

impl Decoder {
    /// Creates an empty decoder.
    #[must_use]
    pub fn new() -> Self {
        Self::default()
    }

    /// Returns the running counters.
    #[must_use]
    pub fn stats(&self) -> DecoderStats {
        self.stats
    }

    /// Returns how many bytes are buffered awaiting a complete frame.
    #[must_use]
    pub fn buffered(&self) -> usize {
        self.buf.len()
    }

    /// Appends received bytes; call `next_packet` or `drain` to consume them.
    pub fn push(&mut self, bytes: &[u8]) {
        tracing::trace!(n = bytes.len(), buffered = self.buf.len(), "decoder push");
        self.buf.extend_from_slice(bytes);
    }

    /// Drops buffered bytes and msgCount tracking (for example after a purge).
    pub fn reset(&mut self) {
        tracing::debug!(discarded = self.buf.len(), "decoder reset");
        self.buf.clear();
        self.last_msg = None;
    }

    /// Returns the next packet (or framing-level parse error), or None if more bytes are needed.
    pub fn next_packet(&mut self) -> Option<Result<Packet, CodecError>> {
        loop {
            let Some(start) = self.buf.iter().position(|&b| b == SYNC) else {
                self.drop_front(self.buf.len());
                return None;
            };
            self.drop_front(start);
            if self.buf.len() < PACKET_LEN {
                return None;
            }
            if self.buf[PACKET_LEN - 4..PACKET_LEN] != TAIL {
                // False sync byte: skip it and rescan.
                self.drop_front(1);
                continue;
            }
            let result = Packet::parse(&self.buf[..PACKET_LEN]);
            self.buf.drain(..PACKET_LEN);
            match &result {
                Ok(p) => {
                    self.stats.packets += 1;
                    self.track(p);
                }
                Err(e) => {
                    self.stats.malformed += 1;
                    tracing::warn!(error = %e, "framed packet failed to parse");
                }
            }
            return Some(result);
        }
    }

    /// Pulls every packet currently available.
    pub fn drain(&mut self) -> Vec<Result<Packet, CodecError>> {
        std::iter::from_fn(|| self.next_packet()).collect()
    }

    fn drop_front(&mut self, n: usize) {
        if n == 0 {
            return;
        }
        self.buf.drain(..n);
        self.stats.dropped_bytes += n as u64;
        tracing::debug!(
            n,
            total = self.stats.dropped_bytes,
            "dropped bytes while resyncing"
        );
    }

    /// Updates msgCount gap accounting; Start zeroes the counter, so non-data packets reset it.
    fn track(&mut self, p: &Packet) {
        let Packet::Data(d) = p else {
            self.last_msg = None;
            return;
        };
        if let Some(last) = self.last_msg {
            if d.msg_count > last.saturating_add(1) {
                let missed = u64::from(d.msg_count - last - 1);
                self.stats.gap_events += 1;
                self.stats.missed_packets += missed;
                tracing::warn!(last, now = d.msg_count, missed, "msgCount gap");
            } else if d.msg_count <= last {
                tracing::debug!(
                    last,
                    now = d.msg_count,
                    "msgCount went back; assuming restart"
                );
            }
        }
        self.last_msg = Some(d.msg_count);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::codec::packet::{DataPacket, DeviceState, Sample, SAMPLES_PER_PACKET};

    fn data(n: u32) -> Vec<u8> {
        Packet::Data(Box::new(DataPacket {
            state: DeviceState::Running,
            digital_inputs: 0,
            msg_count: n,
            samples: [Sample::default(); SAMPLES_PER_PACKET],
        }))
        .encode()
        .to_vec()
    }

    #[test]
    fn counts_msg_gaps() {
        let mut d = Decoder::new();
        for n in [0, 1, 5, 6] {
            d.push(&data(n));
        }
        assert_eq!(d.drain().len(), 4);
        let s = d.stats();
        assert_eq!((s.gap_events, s.missed_packets), (1, 3));
    }

    #[test]
    fn byte_at_a_time_and_garbage() {
        let mut d = Decoder::new();
        let mut stream = vec![0x55, 0x00, 0x55, 0x55];
        stream.extend(data(0));
        let mut got = 0;
        for b in stream {
            d.push(&[b]);
            got += d.drain().len();
        }
        assert_eq!(got, 1);
        assert_eq!(d.stats().dropped_bytes, 4);
    }

    // frob:ticket 01M6W7R0VNQVPZ47CD080SB0TA
    // frob:tests crates/sadi-proto/src/codec/decoder.rs::Decoder.buffered
    // frob:tests crates/sadi-proto/src/codec/decoder.rs::Decoder.reset
    #[test]
    fn buffered_and_reset() {
        let mut d = Decoder::new();
        d.push(&data(0)[..100]);
        assert_eq!(d.buffered(), 100);
        d.reset();
        assert_eq!(d.buffered(), 0);
    }
}
