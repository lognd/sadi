"""WAL record framing, type registry and payload models (data-safety.md section 3)."""

# frob:ticket 01M6W7R1VQHABR51SH64668M06
from __future__ import annotations

import hashlib
import struct
from enum import IntEnum
from typing import Any

from crc32c import crc32c
from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result, propagate

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

FRAME_MAGIC = b"SADR"
FRAME_VERSION = 1
FRAME_HEADER_LEN = 32
MAX_PAYLOAD = 16 * 1024 * 1024
FLAG_JSON = 0x1
FLAG_ZLIB = 0x2
KNOWN_FLAGS = FLAG_JSON | FLAG_ZLIB

# magic(4) version(1) type(1) flags(2) seq(8) wall_ns(8) length(4) crc(4)
_HEADER = struct.Struct("<4sBBHQqII")
_HEADER_NO_CRC = struct.Struct("<4sBBHQqI")
_RAW_JUNK_HEAD = struct.Struct("<HHQI")
_RAW_BLOCK_HEAD = struct.Struct("<HHIqqII")
_SEAL = struct.Struct("<HHIQQ32s")
_PREFIX_ITEM = struct.Struct("<QI")
SEAL_PAYLOAD_LEN = _SEAL.size


class RecordType(IntEnum):
    """Registered record type codes (section 3.3)."""

    SESSION_START = 0x01
    RAW_BLOCK = 0x02
    RAW_JUNK = 0x03
    MARKER = 0x04
    POINT = 0x05
    EDIT = 0x06
    SETTINGS = 0x07
    NOTE = 0x08
    DEVICE_EVENT = 0x09
    SNAPSHOT_REF = 0x0A
    EXPORT_REF = 0x0B
    SESSION_CLOSE = 0x0C
    SEAL = 0x7E
    PAD = 0x7F


# Types whose payload is binary (flags bit 0 must be 0).
BINARY_TYPES = frozenset({RecordType.RAW_BLOCK, RecordType.RAW_JUNK, RecordType.SEAL})


class FrameInvalid(BaseModel):
    """A frame failed structural or CRC verification at a byte offset."""

    model_config = ConfigDict(frozen=True)
    offset: int
    reason: str
    # True when the frame was complete and CRC-valid but semantically wrong (not a torn write).
    crc_valid: bool = False
    hint: str = "The record at this position failed verification."


class Record(BaseModel):
    """One verified (decoded) WAL record; `type` may be an unregistered code (UnknownRecord)."""

    model_config = ConfigDict(frozen=True)
    type: int
    seq: int
    wall_ns: int
    flags: int
    payload: bytes
    crc: int

    @property
    def known(self) -> bool:
        """Return True when `type` is in the registry."""
        return self.type in RecordType._value2member_map_


class NewRecord(BaseModel):
    """A record a producer asks the writer to append; seq and wall_ns are assigned by the WAL."""

    model_config = ConfigDict(frozen=True)
    type: int
    payload: bytes
    flags: int = 0


def json_record(rtype: RecordType, model: BaseModel) -> NewRecord:
    """Build a NewRecord carrying `model` as compact UTF-8 JSON (flags bit 0 set)."""
    return NewRecord(
        type=int(rtype), payload=model.model_dump_json().encode("utf-8"), flags=FLAG_JSON
    )


def encode_frame(rtype: int, seq: int, wall_ns: int, flags: int, payload: bytes) -> bytes:
    """Encode one frame: header, CRC-32C over zero-crc header plus payload, then payload."""
    head = _HEADER_NO_CRC.pack(FRAME_MAGIC, FRAME_VERSION, rtype, flags, seq, wall_ns, len(payload))
    crc = crc32c(payload, crc32c(head + b"\x00\x00\x00\x00"))
    return head + struct.pack("<I", crc) + payload


def frame_crc(frame_header: bytes, payload: bytes) -> int:
    """Return the CRC-32C the frame at `frame_header` (32 bytes) should carry."""
    head = frame_header[:28] + b"\x00\x00\x00\x00"
    return crc32c(payload, crc32c(head))


def parse_header(
    header: bytes, offset: int
) -> Result[tuple[int, int, int, int, int, int], FrameInvalid]:
    """Check a 32-byte header; return (type, flags, seq, wall_ns, length, crc)."""
    magic, version, rtype, flags, seq, wall_ns, length, crc = _HEADER.unpack(header)
    if magic != FRAME_MAGIC:
        return Err(FrameInvalid(offset=offset, reason="bad frame magic"))
    if version != FRAME_VERSION:
        return Err(FrameInvalid(offset=offset, reason=f"unsupported frame version {version}"))
    if flags & ~KNOWN_FLAGS:
        return Err(FrameInvalid(offset=offset, reason=f"reserved flag bits set: {flags:#x}"))
    if rtype == 0 or rtype >= 0x80:
        return Err(FrameInvalid(offset=offset, reason=f"reserved record type {rtype:#x}"))
    if length > MAX_PAYLOAD:
        return Err(FrameInvalid(offset=offset, reason=f"payload length {length} exceeds maximum"))
    return Ok((int(rtype), int(flags), int(seq), int(wall_ns), int(length), int(crc)))


@propagate
def decode_payload_check(
    header: bytes, payload: bytes, offset: int
) -> Result[Record, FrameInvalid]:
    """Verify the CRC of a complete frame (header and payload) and build the Record."""
    parsed = parse_header(header, offset)
    rtype, flags, seq, wall_ns, length, crc = parsed.unwrap()
    if len(payload) != length:
        return Err(FrameInvalid(offset=offset, reason="payload shorter than declared length"))
    if frame_crc(header, payload) != crc:
        return Err(FrameInvalid(offset=offset, reason="CRC-32C mismatch"))
    return Ok(Record(type=rtype, seq=seq, wall_ns=wall_ns, flags=flags, payload=payload, crc=crc))


@propagate
def decode_frame(buf: bytes | memoryview, pos: int = 0) -> Result[tuple[Record, int], FrameInvalid]:
    """Decode the frame at `buf[pos:]`; return the Record and the offset after it."""
    if len(buf) - pos < FRAME_HEADER_LEN:
        return Err(FrameInvalid(offset=pos, reason="partial header"))
    header = bytes(buf[pos : pos + FRAME_HEADER_LEN])
    parsed = parse_header(header, pos)
    length = parsed.unwrap()[4]
    end = pos + FRAME_HEADER_LEN + length
    if end > len(buf):
        return Err(FrameInvalid(offset=pos, reason="partial payload"))
    result = decode_payload_check(header, bytes(buf[pos + FRAME_HEADER_LEN : end]), pos)
    return Ok((result.unwrap(), end))


def prefix_hash_update(h: Any, record: Record) -> None:
    """Fold one verified data record into the section 9.2 prefix hash `h` (seq || crc32c)."""
    h.update(_PREFIX_ITEM.pack(record.seq, record.crc))


def new_prefix_hash() -> Any:
    """Return a fresh prefix-hash accumulator (SHA-256)."""
    return hashlib.sha256()


# ---- binary payloads -------------------------------------------------------------------


class RawJunk(BaseModel):
    """Decoded RAW_JUNK payload (section 3.5)."""

    model_config = ConfigDict(frozen=True)
    mono_ns: int
    reason: int
    data: bytes


def encode_raw_junk(mono_ns: int, reason: int, data: bytes) -> bytes:
    """Encode a RAW_JUNK payload: discarded device bytes with a reason code."""
    return _RAW_JUNK_HEAD.pack(1, 0, mono_ns, reason) + data


def decode_raw_junk(payload: bytes) -> Result[RawJunk, FrameInvalid]:
    """Decode a RAW_JUNK payload."""
    if len(payload) < _RAW_JUNK_HEAD.size:
        return Err(FrameInvalid(offset=0, reason="RAW_JUNK payload too short", crc_valid=True))
    layout, _res, mono_ns, reason = _RAW_JUNK_HEAD.unpack_from(payload)
    if layout != 1:
        return Err(FrameInvalid(offset=0, reason=f"RAW_JUNK layout {layout}", crc_valid=True))
    return Ok(RawJunk(mono_ns=mono_ns, reason=reason, data=payload[_RAW_JUNK_HEAD.size :]))


def encode_raw_block(
    packets: bytes, packet_len: int, mono_ns: int, wall_ns: int, first_msgcount: int, flags: int = 0
) -> bytes:
    """Encode a RAW_BLOCK payload of `len(packets) // packet_len` byte-exact packets."""
    count = len(packets) // packet_len
    head = _RAW_BLOCK_HEAD.pack(1, packet_len, count, mono_ns, wall_ns, first_msgcount, flags)
    return head + packets


class Seal(BaseModel):
    """Decoded SEAL payload (section 4.3)."""

    model_config = ConfigDict(frozen=True)
    record_count: int
    first_seq: int
    last_seq: int
    sha256: bytes


def encode_seal(record_count: int, first_seq: int, last_seq: int, sha256: bytes) -> bytes:
    """Encode a SEAL payload."""
    return _SEAL.pack(1, 0, record_count, first_seq, last_seq, sha256)


def decode_seal(payload: bytes) -> Result[Seal, FrameInvalid]:
    """Decode a SEAL payload."""
    if len(payload) != SEAL_PAYLOAD_LEN:
        return Err(FrameInvalid(offset=0, reason="SEAL payload wrong size", crc_valid=True))
    layout, _res, count, first, last, digest = _SEAL.unpack(payload)
    if layout != 1:
        return Err(FrameInvalid(offset=0, reason=f"SEAL layout {layout}", crc_valid=True))
    return Ok(Seal(record_count=count, first_seq=first, last_seq=last, sha256=digest))


# ---- JSON payload models (extra fields preserved) ----------------------------------------


class _JsonPayload(BaseModel):
    """Base for JSON payloads: schema version `v`, optional note, unknown fields kept."""

    model_config = ConfigDict(frozen=True, extra="allow")
    v: int = 1
    note: str | None = None


class SessionStartV1(_JsonPayload):
    """First record of every version: identity, parent link and parent scan result."""

    session_uuid: str
    parent: str | None = None
    parent_last_seq: int | None = None
    parent_scan: dict[str, Any] | None = None
    code_version: str | None = None
    environment: dict[str, Any] | None = None


class SettingsV1(_JsonPayload):
    """A settings change (ADC range, sample rate, ...); written before the first RAW_BLOCK."""

    scope: str
    key: str
    value: Any
    previous: Any = None


class MarkerV1(_JsonPayload):
    """A timeline marker; `raw_seq` is the RAW_BLOCK current at the marker."""

    kind: str
    label: str = ""
    raw_seq: int | None = None
    data: dict[str, Any] = {}
