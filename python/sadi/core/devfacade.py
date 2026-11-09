"""The only importer of sadi_py: every device exception becomes a typed DeviceError value.

Third-party code (the PyO3 extension, pyserial, the OS) raises, panics and returns
garbage. This facade is the thin low-latency wrapper; everything above it consumes
typani `Result[T, DeviceError]` with an exhaustive `DeviceCode` and a user hint.
Only KeyboardInterrupt/SystemExit and sadi_py phase-contract errors (programmer bugs)
are allowed to propagate.
"""

# frob:ticket 01M6Z3095E9TR8FEQM7Y6MM2ZP

from __future__ import annotations

import errno
import importlib
import sys
import types
from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Final, TypeVar

from typani import Err, Ok, Result

from sadi.core.errors import DeviceCode, DeviceError
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

if TYPE_CHECKING:  # annotation-only alias; runtime access goes through binding()
    import sadi_py as sp  # noqa: F401 - re-exported for annotations

_MODULE: Final[str] = "sadi_py"

T = TypeVar("T")

#: sadi_py error kinds that mean the caller broke the phase contract: a programmer bug, re-raised.
PROGRAMMER_KINDS: Final[frozenset[str]] = frozenset({"phase", "consumed", "busy"})

#: sadi_py error kind -> device failure code (user-facing hint comes from the code).
KIND_TO_CODE: Final[dict[str, DeviceCode]] = {
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
    "codec": DeviceCode.BAD_DATA,
    "other": DeviceCode.PROTOCOL,
}

_DENIED_WORDS: Final[tuple[str, ...]] = ("permission", "denied", "access is denied")
_BUSY_WORDS: Final[tuple[str, ...]] = ("busy", "in use", "locked", "resource temporarily")
_BUSY_ERRNOS: Final[frozenset[int]] = frozenset({errno.EBUSY, errno.EAGAIN})
_GONE_ERRNOS: Final[frozenset[int]] = frozenset(
    {errno.ENODEV, errno.ENXIO, errno.EIO, errno.EPIPE, errno.ENOENT}
)


class SpentPhaseError(RuntimeError):
    """Programmer bug: a phase object was used after a transition consumed it."""


def binding() -> Result[types.ModuleType, DeviceError]:
    """Import sadi_py lazily; Err(BINDING_MISSING) on ImportError, load failure or import panic."""
    try:
        return Ok(importlib.import_module(_MODULE))
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except BaseException as exc:  # noqa: BLE001 - a native import may raise ImportError or panic  # typani: ignore[TYP007]
        _log.warning("sadi_py not importable: %s: %s", type(exc).__name__, exc)
        return Err(
            DeviceError(code=DeviceCode.BINDING_MISSING, detail=f"{type(exc).__name__}: {exc}")
        )


def default_adc_mode() -> Result[Any, DeviceError]:
    """The DLL-compatible ADC mode, resolved lazily so import never needs the binding."""
    return binding().map(lambda mod: mod.AdcMode.DLL_COMPATIBLE)


def _is_sadi_error(exc: BaseException) -> bool:
    """True for a sadi_py.SadiError; False when the binding was never loaded."""
    mod = sys.modules.get(_MODULE)
    base = getattr(mod, "SadiError", None)
    if isinstance(base, type):
        return isinstance(exc, base)
    return False


def _has_word(text: str, words: tuple[str, ...]) -> bool:
    """Case-insensitive substring test against any of `words`."""
    low = text.lower()
    return any(w in low for w in words)


def _code_for_text(text: str, default: DeviceCode) -> DeviceCode:
    """Refine `default` into PERMISSION_DENIED or BUSY when the message says so."""
    if _has_word(text, _DENIED_WORDS):
        return DeviceCode.PERMISSION_DENIED
    if _has_word(text, _BUSY_WORDS):
        return DeviceCode.BUSY
    return default


def _classify_os_error(exc: OSError) -> DeviceCode:
    """Map an OSError (and pyserial's SerialException, an OSError subclass) to a code."""
    if isinstance(exc, PermissionError) or exc.errno in (errno.EACCES, errno.EPERM):
        return DeviceCode.PERMISSION_DENIED
    if isinstance(exc, TimeoutError):
        return DeviceCode.TIMEOUT
    if exc.errno in _BUSY_ERRNOS:
        return DeviceCode.BUSY
    if isinstance(exc, FileNotFoundError) or exc.errno == errno.ENOENT:
        return DeviceCode.NOT_FOUND
    if isinstance(exc, (BrokenPipeError, ConnectionError)) or exc.errno in _GONE_ERRNOS:
        return DeviceCode.DISCONNECTED
    return _code_for_text(str(exc), DeviceCode.DISCONNECTED)


def to_device_error(exc: BaseException) -> DeviceError:
    """Map any third-party exception to a DeviceError; total over every exception type."""
    if _is_sadi_error(exc):
        kind = str(getattr(exc, "kind", "other"))
        detail = str(getattr(exc, "detail", exc))
        base = KIND_TO_CODE.get(kind, DeviceCode.PROTOCOL)
        refine = base in (DeviceCode.DISCONNECTED, DeviceCode.NOT_FOUND)
        code = _code_for_text(detail, base) if refine else base
        _log.warning("sadi_py error kind=%s mapped to %s: %s", kind, code, detail)
        return DeviceError(code=code, detail=f"{kind}: {detail}")
    if isinstance(exc, ImportError):
        code = DeviceCode.BINDING_MISSING
    elif isinstance(exc, OSError):
        code = _classify_os_error(exc)
    elif isinstance(exc, (UnicodeError, ValueError, TypeError, AttributeError, KeyError)):
        code = DeviceCode.BAD_DATA  # garbage frames, wrong shapes, missing block fields
    elif isinstance(exc, (OverflowError, ArithmeticError)):
        code = DeviceCode.BAD_DATA
    else:  # RuntimeError, MemoryError, pyo3 PanicException (a BaseException), anything else
        code = DeviceCode.INTERNAL
    name = type(exc).__name__
    _log.warning("%s mapped to %s: %s", name, code, exc)
    return DeviceError(code=code, detail=f"{name}: {exc}")


def guard(op: str, fn: Callable[[], T]) -> Result[T, DeviceError]:
    """Run a device call; every failure becomes Err, only programmer bugs and exits propagate."""
    try:
        return Ok(fn())
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except SpentPhaseError:
        raise
    except BaseException as exc:  # noqa: BLE001 - the facade IS the catch-all (pyo3 panics)  # typani: ignore[TYP007]
        if _is_sadi_error(exc) and getattr(exc, "kind", None) in PROGRAMMER_KINDS:
            _log.error("programmer bug in %s: %s: %s", op, getattr(exc, "kind", ""), exc)
            raise
        _log.info("%s failed: %s", op, type(exc).__name__)
        return Err(to_device_error(exc))


def close_quietly(op: str, closer: Callable[[], object]) -> Result[None, DeviceError]:
    """Run a close/release call that must never raise; the Err is for logging by the caller."""
    res = guard(op, closer)
    if isinstance(res, Err):
        _log.warning("%s failed during cleanup: %s", op, res.danger_err.detail)
        return Err(res.danger_err)
    return Ok(None)


def check_block(block: Any) -> Result[Any, DeviceError]:
    """Reject a block with NaN/inf volts or columns of unequal length; Ok returns it unchanged."""
    import numpy as np

    def _validate() -> Any:
        n = int(block.n_samples)
        volts = np.asarray(block.volts)
        raw = np.asarray(block.adc_raw)
        if n < 0 or len(volts) != n or len(raw) != n:
            raise ValueError(f"column lengths disagree with n_samples={n}")
        if n and not bool(np.isfinite(volts).all()):
            raise ValueError("non-finite volts in block")
        return block

    return guard("check_block", _validate)
