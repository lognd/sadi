"""Typed stubs for sadi_py.acq: GIL-released acquisition thread with a bounded channel."""

from sadi_py import Block, Session

ACQ_CHANNEL_BLOCKS: int

class AcqMetrics:
    """Point-in-time acquisition counters."""
    @property
    def queue_depth(self) -> int:
        """Blocks currently queued."""
    @property
    def high_water(self) -> int:
        """Highest queue depth seen."""
    @property
    def capacity(self) -> int:
        """Channel capacity in blocks."""
    @property
    def blocks_read(self) -> int:
        """Blocks read from the device."""
    @property
    def blocks_sent(self) -> int:
        """Blocks successfully queued."""
    @property
    def gaps(self) -> int:
        """msgCount gap events seen by the decoder."""
    @property
    def missed_packets(self) -> int:
        """Data packets missing according to msgCount jumps."""
    @property
    def dropped_bytes(self) -> int:
        """Bytes the decoder dropped while resyncing."""
    @property
    def channel_full_waits(self) -> int:
        """Times a block found the channel full (once per block)."""
    @property
    def channel_full_wait_ms(self) -> int:
        """Total milliseconds spent waiting on a full channel."""
    @property
    def blocks_lost(self) -> int:
        """Blocks read but never queued (stop or consumer gone while full)."""
    @property
    def read_timeouts(self) -> int:
        """Read timeouts seen by the thread."""
    @property
    def consumer_stalled(self) -> bool:
        """True once the channel stayed full for more than five seconds."""
    @property
    def state(self) -> str:
        """One of STREAMING, STOPPING, STOPPED, FAILED."""
    @property
    def error(self) -> str | None:
        """Error text when state is FAILED."""

class AcqHandle:
    """Running acquisition thread; takes the streaming stage out of the Session."""
    def __init__(self, session: Session, capacity: int = ...) -> None:
        """Start acquisition on a STREAMING session; the session reports busy meanwhile."""
    def recv_block(self, timeout_ms: int = 20) -> Block | None:
        """Wait (GIL released) for a block; None on timeout; RuntimeError once ended and drained."""
    def try_recv_block(self) -> Block | None:
        """Return a queued block immediately or None."""
    def stop(self) -> None:
        """Request the thread to stop (non-blocking, idempotent)."""
    def metrics(self) -> AcqMetrics:
        """Current counters."""
    def join(self) -> AcqMetrics:
        """Stop, join (GIL released), return the session to STREAMING, yield final counters."""
