"""Binary WebSocket frame codec: byte-for-byte layout in docs/server/websocket.md.

All integers and floats are little-endian. Every frame starts with a fixed 24-byte header;
the decoder here is the reference the TypeScript decoder mirrors.
"""

# frob:ticket 01M6W7R3ZPY606D3MHG4QRM2GS

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

import numpy as np
from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

MAGIC = b"SADI"
VERSION = 1
#: magic(4s) version(B) type(B) flags(H) seq(Q) t0_s(d)
HEADER = struct.Struct("<4sBBHQd")
#: raw_seq(Q) durable_seq(Q) enqueued_seq(Q) dt_s(d) n_channels(H) n_points(I)
TRACE_HEAD = struct.Struct("<QQQdHI")
#: channel id (H), followed by 2 * n_points float32 (min, max interleaved)
CHANNEL_ID = struct.Struct("<H")
FLAG_STALE = 0x0001


class FrameType(IntEnum):
    """Binary frame types; JSON side-channel messages travel as WebSocket text, not here."""

    TRACE = 1
    #: Reserved for the versioned results envelope (J4); payload is UTF-8 JSON.
    RESULTS_ENVELOPE = 2


class FrameError(ErrorSet):
    """Why a binary frame could not be decoded."""

    SHORT = "frame shorter than its header or declared payload"
    MAGIC = "bad magic; not a SADI frame"
    VERSION = "unsupported frame version"
    TYPE = "unknown frame type"


@dataclass(frozen=True)
class TraceData:
    """Decoded trace payload: per-channel (min, max) arrays of equal length."""

    raw_seq: int
    durable_seq: int
    enqueued_seq: int
    dt_s: float
    mins: dict[int, np.ndarray]
    maxs: dict[int, np.ndarray]


@dataclass(frozen=True)
class Frame:
    """A decoded frame: header fields plus `trace` (TRACE) or `body` (RESULTS_ENVELOPE)."""

    type: FrameType
    flags: int
    seq: int
    t0_s: float
    trace: TraceData | None = None
    body: bytes = b""

    @property
    def stale(self) -> bool:
        """True when the stale flag is set."""
        return bool(self.flags & FLAG_STALE)


def minmax_decimate(values: np.ndarray, max_points: int) -> tuple[np.ndarray, np.ndarray]:
    """Reduce `values` to at most `max_points` (min, max) float32 pairs, keeping peaks."""
    v = np.asarray(values, dtype=np.float32)
    n = v.shape[0]
    if n <= max_points:
        return v, v
    edges = np.linspace(0, n, max_points + 1).astype(np.int64)
    mins = np.minimum.reduceat(v, edges[:-1])
    maxs = np.maximum.reduceat(v, edges[:-1])
    return mins, maxs


def encode_trace(  # noqa: PLR0913 - the frame fields are the wire format
    seq: int,
    t0_s: float,
    dt_s: float,
    channels: dict[int, list[float]],
    raw_seq: int,
    durable_seq: int,
    enqueued_seq: int,
    max_points: int = 256,
) -> bytes:
    """Encode a TRACE frame, min/max-decimating each channel to at most `max_points`."""
    decimated = {c: minmax_decimate(np.asarray(v), max_points) for c, v in sorted(channels.items())}
    n_points = max((m.shape[0] for m, _ in decimated.values()), default=0)
    out = bytearray(HEADER.pack(MAGIC, VERSION, FrameType.TRACE, 0, seq, t0_s))
    out += TRACE_HEAD.pack(raw_seq, durable_seq, enqueued_seq, dt_s, len(decimated), n_points)
    for ch, (mn, mx) in decimated.items():
        pad = n_points - mn.shape[0]
        if pad:
            mn, mx = np.pad(mn, (0, pad), mode="edge"), np.pad(mx, (0, pad), mode="edge")
        out += CHANNEL_ID.pack(ch)
        out += np.stack([mn, mx], axis=1).astype("<f4").tobytes()
    return bytes(out)


def encode_envelope(seq: int, t0_s: float, body: bytes, *, stale: bool = False) -> bytes:
    """Encode a RESULTS_ENVELOPE frame carrying the J4 JSON `body` and the stale flag."""
    flags = FLAG_STALE if stale else 0
    return HEADER.pack(MAGIC, VERSION, FrameType.RESULTS_ENVELOPE, flags, seq, t0_s) + body


def decode(data: bytes) -> Result[Frame, FrameError]:
    """Decode one binary frame."""
    if len(data) < HEADER.size:
        return Err(FrameError.SHORT)
    magic, version, ftype, flags, seq, t0 = HEADER.unpack_from(data)
    if magic != MAGIC:
        return Err(FrameError.MAGIC)
    if version != VERSION:
        return Err(FrameError.VERSION)
    try:
        kind = FrameType(ftype)
    except ValueError:
        return Err(FrameError.TYPE)
    rest = data[HEADER.size :]
    if kind is FrameType.RESULTS_ENVELOPE:
        return Ok(Frame(kind, flags, seq, t0, body=bytes(rest)))
    if len(rest) < TRACE_HEAD.size:
        return Err(FrameError.SHORT)
    raw_seq, durable, enq, dt_s, n_ch, n_pts = TRACE_HEAD.unpack_from(rest)
    stride = CHANNEL_ID.size + 8 * n_pts
    if len(rest) != TRACE_HEAD.size + n_ch * stride:
        return Err(FrameError.SHORT)
    mins: dict[int, np.ndarray] = {}
    maxs: dict[int, np.ndarray] = {}
    off = TRACE_HEAD.size
    for _ in range(n_ch):
        (ch,) = CHANNEL_ID.unpack_from(rest, off)
        arr = np.frombuffer(rest, dtype="<f4", count=2 * n_pts, offset=off + CHANNEL_ID.size)
        mins[ch], maxs[ch] = arr[0::2].copy(), arr[1::2].copy()
        off += stride
    trace = TraceData(raw_seq, durable, enq, dt_s, mins, maxs)
    return Ok(Frame(kind, flags, seq, t0, trace=trace))
