"""Typed session phases over sadi_py.Session; each transition consumes the old object."""

# frob:ticket 01M6X572N6WB1053QZ1WV4W4WY
# frob:ticket 01M6W7R2NWFTQBK7FRWGX511CP

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Final, TypeVar

import sadi_py as sp
from typani import Err, Ok, Result

from sadi.core.errors import DeviceCode, DeviceError
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

T = TypeVar("T")

#: sadi_py error kinds that mean the caller broke the phase contract: a programmer bug, re-raised.
_PROGRAMMER_KINDS: Final[frozenset[str]] = frozenset({"phase", "consumed", "busy"})

#: sadi_py error kind -> device failure code (user-facing hint comes from the code).
_KIND_TO_CODE: Final[dict[str, DeviceCode]] = {
    "config": DeviceCode.NOT_FOUND,
    "scenario": DeviceCode.NOT_FOUND,
    "transport_timeout": DeviceCode.TIMEOUT,
    "command_timeout": DeviceCode.TIMEOUT,
    "read_timeout": DeviceCode.TIMEOUT,
    "transport_closed": DeviceCode.DISCONNECTED,
    "transport_io": DeviceCode.DISCONNECTED,
    "transport_overflow": DeviceCode.PROTOCOL,
    "unexpected_state": DeviceCode.PROTOCOL,
    "tap": DeviceCode.PROTOCOL,
    "codec": DeviceCode.PROTOCOL,
    "other": DeviceCode.PROTOCOL,
}


class SpentPhaseError(RuntimeError):
    """Programmer bug: a phase object was used after a transition consumed it."""


def to_device_error(exc: sp.SadiError) -> DeviceError:
    """Map a sadi_py error to a DeviceError (code carries the 'what to do' hint)."""
    code = _KIND_TO_CODE.get(exc.kind, DeviceCode.PROTOCOL)
    _log.warning("sadi_py error kind=%s mapped to %s: %s", exc.kind, code, exc.detail)
    return DeviceError(code=code, detail=f"{exc.kind}: {exc.detail}")


def guard(op: str, fn: Callable[[], T]) -> Result[T, DeviceError]:
    """Run a sadi_py call; device failures become Err, phase-misuse errors are re-raised."""
    try:
        return Ok(fn())
    except sp.SadiError as exc:
        if exc.kind in _PROGRAMMER_KINDS:
            _log.error("programmer bug in %s: %s: %s", op, exc.kind, exc.detail)
            raise
        _log.info("%s failed", op)
        return Err(to_device_error(exc))


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
        return guard("read_block", self._live().read_block)

    def stop(self) -> Result[tuple[Stopped, sp.Block], DeviceError]:
        """Stop streaming; Ok consumes self and returns the trailing block."""
        session = self._live()
        res = guard("stop", session.stop)
        if isinstance(res, Err):
            return Err(res.danger_err)
        self._spend()
        _log.info("streaming stopped")
        return Ok((Stopped(session), res.danger_ok))


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
    return guard("open_sim", lambda: sp.open_sim(scenario, seed, cfg)).map(Disconnected)


def open_sim_controlled(
    scenario: str,
    seed: int | None = None,
    cfg: sp.SessionConfig | None = None,
    manual_load: bool = False,
) -> Result[tuple[Disconnected, sp.sim.SimControl], DeviceError]:
    """Open a simulator plus its live control; `manual_load` clears the timed load program."""

    def _open() -> tuple[sp.Session, sp.sim.SimControl]:
        session, ctl = sp.sim.open(scenario, seed, cfg)
        if manual_load:
            ctl.set_load_program([(0.0, 0.0)])
        return session, ctl

    return guard("open_sim_controlled", _open).map(lambda sc: (Disconnected(sc[0]), sc[1]))


def open_serial(
    port: str, cfg: sp.SessionConfig | None = None
) -> Result[Disconnected, DeviceError]:
    """Open a serial session in the Disconnected phase."""
    return guard("open_serial", lambda: sp.open_serial(port, cfg)).map(Disconnected)


def list_ports() -> Result[list[sp.PortInfo], DeviceError]:
    """List serial ports visible to the binding."""
    return guard("ports", sp.ports)
