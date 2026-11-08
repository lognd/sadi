"""Filename sanitiser for user-derived names (portability section 5).

Turns arbitrary text (specimen id, session title) into a name that is a valid single path
component on Windows, Linux and macOS. Sanitising is lossy, so every name that had to change
carries a deterministic hash suffix of the raw text: two distinct raw names never collapse to
one silently. `unique_name` additionally checks against names already present and never
returns one of them, so an existing file or directory is never overwritten.
"""

# frob:ticket 01M6WA536YCYA3FZB2JT5XVYE8
from __future__ import annotations

import hashlib
import re
from collections.abc import Collection

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

DEFAULT_MAX_LEN = 64
MIN_MAX_LEN = 24
FALLBACK_BASE = "unnamed"
_HASH_LEN = 10
_SUFFIX_LEN = _HASH_LEN + 1  # "~" + hash
_MAX_COUNTER = 9999
_BAD_CHAR_RE = re.compile(r"[^A-Za-z0-9._~-]")
_VALID_RE = re.compile(r"[A-Za-z0-9._~-]+")
_RESERVED = frozenset(
    {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(10)} | {f"LPT{i}" for i in range(10)}
)


class NameFailure(BaseModel):
    """Base of the name-sanitiser error variants."""

    model_config = ConfigDict(frozen=True)


class NameExhausted(NameFailure):
    """Every disambiguation candidate for `base` is already taken."""

    base: str


def _is_reserved(name: str) -> bool:
    """Return True if the part before the first dot is a Windows device name."""
    return name.split(".", 1)[0].upper() in _RESERVED


def is_safe_name(name: str, max_len: int = DEFAULT_MAX_LEN) -> bool:
    """Return True if `name` is already a valid portable path component."""
    return (
        0 < len(name) <= max_len
        and _VALID_RE.fullmatch(name) is not None
        and not name.endswith(".")
        and not _is_reserved(name)
    )


def _digest(raw: str) -> str:
    """Return the short deterministic hash of the raw text."""
    return hashlib.sha256(raw.encode("utf-8", "surrogatepass")).hexdigest()[:_HASH_LEN]


def sanitize_name(raw: str, max_len: int = DEFAULT_MAX_LEN) -> str:
    """Map `raw` to a portable name; valid input is returned unchanged, otherwise hash-suffixed."""
    if max_len < MIN_MAX_LEN:
        raise ValueError(f"max_len must be >= {MIN_MAX_LEN}, got {max_len}")
    if is_safe_name(raw, max_len):
        return raw
    base = _BAD_CHAR_RE.sub("_", raw).rstrip(".") or FALLBACK_BASE
    if _is_reserved(base):
        base = f"_{base}"
    base = base[: max_len - _SUFFIX_LEN].rstrip(".") or FALLBACK_BASE
    out = f"{base}~{_digest(raw)}"
    _log.info("sanitised name %r -> %r", raw, out)
    return out


def unique_name(
    raw: str, taken: Collection[str], max_len: int = DEFAULT_MAX_LEN
) -> Result[str, NameExhausted]:
    """Sanitise `raw`; the result never case-insensitively matches a name in `taken`."""
    taken_ci = {t.casefold() for t in taken}
    first = sanitize_name(raw, max_len)
    if first.casefold() not in taken_ci:
        return Ok(first)
    stem = first[: max_len - 5]
    for n in range(2, _MAX_COUNTER + 1):
        cand = f"{stem}~{n}"
        if cand.casefold() not in taken_ci and is_safe_name(cand, max_len):
            _log.warning("name %r taken, using %r", first, cand)
            return Ok(cand)
    _log.error("no free name for %r after %d tries", first, _MAX_COUNTER)
    return Err(NameExhausted(base=first))
