"""Opt-in gate for the synthetic source: an explicit flag AND the typed confirmation phrase."""

# frob:ticket 01M71SYG3H3X7GJT21TE6MY8YC
from __future__ import annotations

from typani import Err, ErrorSet, Ok, Result

from sadi.logging_setup import get_logger
from sadi.synthetic.provenance import CONFIRM_PHRASE

_log = get_logger(__name__)

__all__ = ["EnableError", "check_enable"]


class EnableError(ErrorSet):
    """Why the synthetic source was not enabled; the description says what to do."""

    NoFlag = "The confirmation phrase was given without --synthetic-specimen; nothing enabled"
    NoPhrase = (
        "--synthetic-specimen needs the typed confirmation phrase: "
        f'--i-understand-this-is-fake="{CONFIRM_PHRASE}"'
    )
    WrongPhrase = f'The confirmation phrase must be typed exactly: "{CONFIRM_PHRASE}"'


def check_enable(flag: bool, phrase: str | None) -> Result[bool, EnableError]:
    """Ok(True) only for flag AND exact phrase; Ok(False) when neither; Err on a half-given pair."""
    if not flag:
        if phrase is not None:
            _log.warning("synthetic phrase given without the flag; refusing")
            return Err(EnableError.NoFlag)
        return Ok(False)
    if phrase is None:
        _log.warning("synthetic flag given without the phrase; refusing")
        return Err(EnableError.NoPhrase)
    if phrase != CONFIRM_PHRASE:
        _log.warning("synthetic confirmation phrase does not match; refusing")
        return Err(EnableError.WrongPhrase)
    _log.warning("SYNTHETIC SPECIMEN ENABLED: all data will be labelled synthetic")
    return Ok(True)
