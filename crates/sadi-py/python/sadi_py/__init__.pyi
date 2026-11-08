"""Typed stubs for sadi_py (native module `sadi_py._native`)."""

import enum
from typing import Final, Literal, Sequence

import numpy as np
import numpy.typing as npt

Kind = Literal[
    "config", "transport_timeout", "transport_closed", "transport_overflow",
    "transport_io", "command_timeout", "read_timeout", "unexpected_state",
    "tap", "codec", "scenario", "phase", "consumed", "busy", "other",
]

class SadiError(Exception):
    """Base of every sadi_py error; carries .kind and .detail."""
    kind: Kind
    detail: str

class ConfigurationError(SadiError):
    """Invalid configuration."""
class TransportFailure(SadiError):
    """Transport-level failure (timeout, closed, overflow, io)."""
class CommandTimeoutError(SadiError):
    """A command got no reply in time."""
class ReadTimeoutError(SadiError):
    """A block read got no data in time."""
class UnexpectedStateError(SadiError):
    """Device reported an unexpected state."""
class TapError(SadiError):
    """Raw-byte tap failure."""
class CodecFailure(SadiError):
    """Frame encode or decode failure."""
class ScenarioFailure(SadiError):
    """Simulator scenario could not be loaded."""
class PhaseError(SadiError):
    """Operation not allowed in the current session phase."""
class ConsumedError(SadiError):
    """Session handle was already consumed."""
class BusyError(SadiError):
    """Session is busy in another call."""

class AdcRange(enum.Enum):
    """ADC input range per channel."""
    PM10_24 = ...
    PM5_12 = ...
    PM2_56 = ...
    PM1_28 = ...
    PM0_64 = ...
    UNIPOLAR10_24 = ...
    UNIPOLAR5_12 = ...
    UNIPOLAR2_56 = ...
    UNIPOLAR1_28 = ...

class AdcMode(enum.Enum):
    """ADC code-to-volts convention."""
    DLL_COMPATIBLE = ...
    IDEAL = ...

class Handshake(enum.Enum):
    """Connect handshake sequence."""
    QUERY_RESET_QUERY = ...
    QUERY_ONLY = ...

class Idempotence(enum.Enum):
    """Whether repeated commands are re-sent."""
    SKIP_IF_ALREADY = ...
    ALWAYS_SEND = ...

class CommandKind(enum.Enum):
    """Wire command kinds."""
    QUERY = ...
    RESET = ...
    START = ...
    STOP = ...

class DeviceState(enum.Enum):
    """Device state reported in packets."""
    BOOTED = ...
    STOPPED = ...
    RUNNING = ...
    UNKNOWN = ...

class Phase(enum.Enum):
    """Session lifecycle phase."""
    DISCONNECTED = ...
    CONNECTED = ...
    STREAMING = ...
    STOPPED = ...
    CLOSED = ...

class PacketKind(enum.Enum):
    """Wire packet kinds."""
    VERSION = ...
    DATA = ...
    STOP_ACK = ...

class Block:
    """One read: raw wire bytes plus decoded columns."""
    raw: bytes
    volts: npt.NDArray[np.float64]  # (n, 4)
    adc_raw: npt.NDArray[np.uint16]  # (n, 4)
    encoder: npt.NDArray[np.int32]  # (n,)
    msg_count: npt.NDArray[np.uint32]  # (packets,)
    digital_inputs: npt.NDArray[np.uint8]  # (packets,)
    n_samples: int
    dropped_bytes: int
    malformed: int
    gap_events: int
    missed_packets: int
    device_state: DeviceState | None
    device_state_byte: int | None
    def __len__(self) -> int:
        """Number of samples."""

class VersionInfo:
    """Firmware version reply."""
    state: DeviceState
    state_byte: int
    major: int
    minor: int
    @property
    def fw_version(self) -> float:
        """Construct."""

class SessionConfig:
    """Optional session tuning; unset fields use protocol defaults."""
    read_timeout_ms: int | None
    command_interval_ms: int | None
    command_timeout_ms: int | None
    idempotence: Idempotence | None
    handshake: Handshake | None
    baud: int | None
    io_timeout_ms: int | None
    rx_limit: int | None
    def __init__(
        self,
        *,
        read_timeout_ms: int | None = None,
        command_interval_ms: int | None = None,
        command_timeout_ms: int | None = None,
        idempotence: Idempotence | None = None,
        handshake: Handshake | None = None,
        baud: int | None = None,
        io_timeout_ms: int | None = None,
        rx_limit: int | None = None,
    ) -> None:
        """Construct."""

class PortInfo:
    """One discovered serial port."""
    name: str
    vid: int
    pid: int
    product: str | None

class PacketInfo:
    """Decoded packet header."""
    kind: PacketKind
    state: DeviceState
    state_byte: int

class Session:
    """One device session; phases are checked at runtime."""
    @property
    def phase(self) -> Phase:
        """Current lifecycle phase."""
    @property
    def description(self) -> str:
        """Human-readable device description."""
    def connect(self) -> None:
        """Run the handshake and enter the connected phase."""
    def query(self) -> VersionInfo:
        """Query firmware version."""
    def reset(self) -> VersionInfo:
        """Reset the device and return its version."""
    def start(self, adc_mode: AdcMode, ranges: Sequence[AdcRange] | None = None) -> None:
        """Begin streaming in the given ADC mode."""
    def read_block(self) -> Block:
        """Read one block (raw bytes plus numpy columns) with the GIL released."""
    def stop(self) -> Block:
        """Stop streaming; returns the trailing block."""
    def restart(self) -> None:
        """Restart streaming after a stop."""
    def disconnect(self) -> None:
        """Leave the connected phase."""
    def close(self) -> None:
        """Consume the session and release the port."""
    def __enter__(self) -> Session:
        """Enter the context manager."""
    def __exit__(self, exc_type: object = None, exc: object = None, tb: object = None) -> bool:
        """Close the session on exit."""

def open_serial(port: str, cfg: SessionConfig | None = None) -> Session:
    """Open a session on a serial port."""
def open_sim(scenario: str, seed: int | None = None, cfg: SessionConfig | None = None) -> Session:
    """Open a session on the simulator."""
def ports() -> list[PortInfo]:
    """List serial ports."""
def encode_command(kind: CommandKind, ranges: Sequence[AdcRange] | None = None) -> bytes:
    """Encode a command frame."""
def decode_packet(frame: bytes) -> PacketInfo:
    """Decode a packet header."""
def decode_data_packet(frame: bytes, adc_mode: AdcMode, ranges: Sequence[AdcRange] | None = None) -> Block:
    """Decode a data packet into a Block."""
def adc_to_volts(raw: int, range: AdcRange, adc_mode: AdcMode) -> float:
    """Convert one raw ADC code to volts."""

class sim:
    """Simulator helpers (registered stub; populated by later tickets)."""

__all__: Final[list[str]]
