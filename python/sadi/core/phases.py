"""Typed session phases over sadi_py.Session; each transition consumes the old object."""

# frob:ticket 01M6X572N6WB1053QZ1WV4W4WY
# frob:ticket 01M6W7R2NWFTQBK7FRWGX511CP
# frob:ticket 01M6Z3095E9TR8FEQM7Y6MM2ZP

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from typani import Err, Ok, Result

from sadi.core.devfacade import (
    SpentPhaseError,
    binding,
    check_block,
    guard,
    to_device_error,
)
from sadi.core.errors import DeviceError
from sadi.logging_setup import get_logger

if TYPE_CHECKING:
    from sadi.core.devfacade import sp

_log = get_logger(__name__)

__all__ = [
    "Connected",
    "Disconnected",
    "SpentPhaseError",
    "Stopped",
    "Streaming",
    "guard",
    "list_ports",
    "open_serial",
    "open_sim",
    "open_sim_controlled",
    "to_device_error",
]


class _Phase:
    """Shared spent-flag logic; `_take` yields the session and `_spend` marks the object used."""

    def __init__(self, session: sp.Session) -> None:
        """Wrap a native session in the phase it is currently in."""
        self._session: sp.Session | None = session
        self._spent = False

    @property
    def spent(self) -> bool:
        """True once a transition has consumed this object."""
        return self._spent

    def _live(self) -> sp.Session:
        """Return the session or raise SpentPhaseError if this object was consumed."""
        if self._spent or self._session is None:
            _log.error("use of spent %s", type(self).__name__)
            raise SpentPhaseError(f"{type(self).__name__} was already consumed by a transition")
        return self._session

    def _spend(self) -> sp.Session:
        """Mark this object consumed and hand the session to the successor."""
        session = self._live()
        self._spent = True
        self._session = None
        _log.debug("%s spent", type(self).__name__)
        return session

    @property
    def description(self) -> str:
        """Human-readable device description from the native session."""
        return self._live().description


class Disconnected(_Phase):
    """Opened but not handshaken; connect() moves to Connected."""

    def connect(self) -> Result[Connected, DeviceError]:
        """Run the handshake; Ok consumes self, Err leaves self usable for a retry."""
        session = self._live()
        res = guard("connect", session.connect)
        if isinstance(res, Err):
            return Err(res.danger_err)
        self._spend()
        _log.info("connected: %s", session.description)
        return Ok(Connected(session))

    def close(self) -> Result[None, DeviceError]:
        """Release the port; consumes self on success."""
        session = self._live()
        res = guard("close", session.close)
        if isinstance(res, Ok):
            self._spend()
        return res


class Connected(_Phase):
    """Handshake done; query, start streaming, disconnect or close."""

    def query(self) -> Result[sp.VersionInfo, DeviceError]:
        """Query the firmware version without changing phase."""
        return guard("query", self._live().query)

    def start(
        self, adc_mode: sp.AdcMode, ranges: Sequence[sp.AdcRange] | None = None
    ) -> Result[Streaming, DeviceError]:
        """Begin streaming; Ok consumes self, Err leaves self usable."""
        session = self._live()
        res = guard("start", lambda: session.start(adc_mode, ranges))
        if isinstance(res, Err):
            return Err(res.danger_err)
        self._spend()
        _log.info("streaming started")
        return Ok(Streaming(session))

    def disconnect(self) -> Result[Disconnected, DeviceError]:
        """Leave the connected phase; Ok consumes self."""
        session = self._live()
        res = guard("disconnect", session.disconnect)
        if isinstance(res, Err):
            return Err(res.danger_err)
        self._spend()
        return Ok(Disconnected(session))

    def close(self) -> Result[None, DeviceError]:
        """Release the port; consumes self on success."""
        session = self._live()
        res = guard("close", session.close)
        if isinstance(res, Ok):
            self._spend()
        return res


class Streaming(_Phase):
    """Device is streaming; read blocks or stop."""

    def read_block(self) -> Result[sp.Block, DeviceError]:
        """Read one block (raw bytes plus numpy columns); stays in Streaming."""
        return guard("read_block", self._live().read_block).and_then(check_block)

    def stop(self) -> Result[tuple[Stopped, sp.Block], DeviceError]:
        """Stop streaming; Ok consumes self and returns the trailing block."""
        session = self._live()
        res = guard("stop", session.stop)
        if isinstance(res, Err):
            return Err(res.danger_err)
        self._spend()
        _log.info("streaming stopped")
        return Ok((Stopped(session), res.danger_ok))

    def force_close(self) -> Result[None, DeviceError]:
        """Release the port without a stop handshake (failed stop, teardown); consumes self."""
        session = self._live()
        res = guard("force_close", session.close)
        self._spend()  # the session is unusable either way; never leave a half-live object
        return res


class Stopped(_Phase):
    """Streaming stopped; restart to Connected or close."""

    def restart(self) -> Result[Connected, DeviceError]:
        """Return to Connected; Ok consumes self."""
        session = self._live()
        res = guard("restart", session.restart)
        if isinstance(res, Err):
            return Err(res.danger_err)
        self._spend()
        return Ok(Connected(session))

    def close(self) -> Result[None, DeviceError]:
        """Release the port; consumes self on success."""
        session = self._live()
        res = guard("close", session.close)
        if isinstance(res, Ok):
            self._spend()
        return res


def open_sim(
    scenario: str, seed: int | None = None, cfg: sp.SessionConfig | None = None
) -> Result[Disconnected, DeviceError]:
    """Open a simulator session in the Disconnected phase."""
    return (
        binding()
        .and_then(lambda mod: guard("open_sim", lambda: mod.open_sim(scenario, seed, cfg)))
        .map(Disconnected)
    )


def open_sim_controlled(
    scenario: str,
    seed: int | None = None,
    cfg: sp.SessionConfig | None = None,
    manual_load: bool = False,
) -> Result[tuple[Disconnected, sp.sim.SimControl], DeviceError]:
    """Open a simulator plus its live control; `manual_load` clears the timed load program."""

    def _open(mod: Any) -> tuple[Any, Any]:
        session, ctl = mod.sim.open(scenario, seed, cfg)
        if manual_load:
            ctl.set_load_program([(0.0, 0.0)])
        return session, ctl

    return (
        binding()
        .and_then(lambda mod: guard("open_sim_controlled", lambda: _open(mod)))
        .map(lambda sc: (Disconnected(sc[0]), sc[1]))
    )


def open_serial(
    port: str, cfg: sp.SessionConfig | None = None
) -> Result[Disconnected, DeviceError]:
    """Open a serial session in the Disconnected phase."""
    return (
        binding()
        .and_then(lambda mod: guard("open_serial", lambda: mod.open_serial(port, cfg)))
        .map(Disconnected)
    )


def list_ports() -> Result[list[sp.PortInfo], DeviceError]:
    """List serial ports visible to the binding."""
    return binding().and_then(lambda mod: guard("ports", mod.ports))
