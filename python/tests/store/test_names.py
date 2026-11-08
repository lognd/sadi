"""Tests for the filename sanitiser: Windows rules, idempotence, collision safety."""

# frob:ticket 01M6WA536YCYA3FZB2JT5XVYE8
from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st
from typani import Err, Ok

from sadi.store.names import (
    DEFAULT_MAX_LEN,
    MIN_MAX_LEN,
    NameExhausted,
    is_safe_name,
    sanitize_name,
    unique_name,
)

_FORBIDDEN = set('<>:"/\\|?*')


def _windows_ok(name: str) -> bool:
    """Independent Win32/POSIX/macOS validity check (not sharing code with the module)."""
    if not name or name in {".", ".."} or name[-1] in ". ":
        return False
    if any(c in _FORBIDDEN or ord(c) < 32 or ord(c) > 126 for c in name):
        return False
    stem = name.split(".")[0].rstrip(" ").upper()
    return stem not in {"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(10)} | {
        f"LPT{i}" for i in range(10)
    }


# frob:tests python/sadi/store/names.py::sanitize_name
@given(st.text(), st.integers(min_value=MIN_MAX_LEN, max_value=200))
def test_output_valid_everywhere(raw: str, max_len: int) -> None:
    out = sanitize_name(raw, max_len)
    assert _windows_ok(out)
    assert len(out) <= max_len
    assert is_safe_name(out, max_len)


# frob:tests python/sadi/store/names.py::sanitize_name
@given(st.text())
def test_idempotent(raw: str) -> None:
    once = sanitize_name(raw)
    assert sanitize_name(once) == once


# frob:tests python/sadi/store/names.py::sanitize_name
@given(st.text(), st.text())
def test_distinct_inputs_stay_distinct(a: str, b: str) -> None:
    if a != b:
        assert sanitize_name(a) != sanitize_name(b)


# frob:tests python/sadi/store/names.py::sanitize_name
@pytest.mark.parametrize(
    "raw",
    [
        "CON",
        "con",
        "NUL.txt",
        "com1",
        "LPT9.tar.gz",
        "aux.",
        "COM0",
        "",
        ".",
        "..",
        "a b",
        "a:b",
        "x" * 500,
        "café",
        "a\x00b",
    ],
)
def test_known_hazards(raw: str) -> None:
    out = sanitize_name(raw)
    assert _windows_ok(out)
    assert out != raw


# frob:tests python/sadi/store/names.py::sanitize_name
def test_valid_name_unchanged() -> None:
    assert sanitize_name("specimen-01_a.b") == "specimen-01_a.b"
    assert sanitize_name("CONSOLE") == "CONSOLE"


# frob:tests python/sadi/store/names.py::sanitize_name
def test_collision_of_lossy_forms_is_disambiguated() -> None:
    assert sanitize_name("a:b") != sanitize_name("a?b")


# frob:tests python/sadi/store/names.py::sanitize_name
def test_small_max_len_is_programmer_error() -> None:
    with pytest.raises(ValueError):
        sanitize_name("x", MIN_MAX_LEN - 1)


# frob:tests python/sadi/store/names.py::unique_name
@given(st.text(), st.sets(st.text(), max_size=5))
def test_unique_never_returns_taken(raw: str, taken: set[str]) -> None:
    res = unique_name(raw, taken)
    assert isinstance(res, Ok)
    assert res.unwrap().casefold() not in {t.casefold() for t in taken}
    assert _windows_ok(res.unwrap())


# frob:tests python/sadi/store/names.py::unique_name
def test_unique_case_insensitive_and_chained() -> None:
    first = unique_name("Spec", ["spec"]).unwrap()
    assert first.casefold() != "spec"
    second = unique_name("Spec", ["spec", first]).unwrap()
    assert second not in {"spec", first}
    assert len(second) <= DEFAULT_MAX_LEN


# frob:tests python/sadi/store/names.py::unique_name
def test_unique_exhaustion_is_err() -> None:
    taken = {"x"} | {f"x~{n}" for n in range(2, 10000)}
    res = unique_name("x", taken)
    assert isinstance(res, Err)
    assert isinstance(res.unwrap_err(), NameExhausted)
