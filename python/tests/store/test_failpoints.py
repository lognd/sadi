"""Tests for the failpoint registry."""

from __future__ import annotations

import errno
from collections.abc import Iterator

import pytest

from sadi.store import failpoints
from sadi.store.failpoints import configure, failpoint


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    """Leave the registry empty around every test."""
    failpoints.clear()
    yield
    failpoints.clear()


# frob:tests python/sadi/store/failpoints.py::failpoint
def test_inactive_is_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    """With nothing armed a hit does nothing."""
    monkeypatch.delenv(failpoints.ENV_VAR, raising=False)
    failpoint("x")


# frob:tests python/sadi/store/failpoints.py::failpoint
def test_error_action_raises_oserror() -> None:
    """error:<errno> raises OSError with that errno."""
    configure({"x": "error:28"})
    with pytest.raises(OSError) as ei:
        failpoint("x")
    assert ei.value.errno == errno.ENOSPC
    failpoint("other")


# frob:tests python/sadi/store/failpoints.py::failpoint
def test_once_and_nth() -> None:
    """once fires on the first hit only; nth fires on exactly the n-th."""
    configure({"a": "once:error:5", "b": "nth:2:error:5"})
    with pytest.raises(OSError):
        failpoint("a")
    failpoint("a")
    failpoint("b")
    with pytest.raises(OSError):
        failpoint("b")
    failpoint("b")


# frob:tests python/sadi/store/failpoints.py::failpoint
def test_prob_zero_never_fires() -> None:
    """prob:0 never fires."""
    configure({"p": "prob:0:error:5"})
    for _ in range(20):
        failpoint("p")


# frob:tests python/sadi/store/failpoints.py::failpoint
def test_sleep_action(monkeypatch: pytest.MonkeyPatch) -> None:
    """sleep:<ms> sleeps for that many milliseconds."""
    slept: list[float] = []
    monkeypatch.setattr(failpoints.time, "sleep", slept.append)
    configure({"s": "sleep:250"})
    failpoint("s")
    assert slept == [0.25]


# frob:tests python/sadi/store/failpoints.py::failpoint
def test_env_loading(monkeypatch: pytest.MonkeyPatch) -> None:
    """SADI_FAILPOINTS is parsed lazily on first hit."""
    monkeypatch.setenv(failpoints.ENV_VAR, "e=error:5, f=error:28")
    with pytest.raises(OSError) as ei:
        failpoint("f")
    assert ei.value.errno == errno.ENOSPC


# frob:tests python/sadi/store/failpoints.py::failpoint
def test_bad_action_rejected() -> None:
    """Unknown actions are a programmer error."""
    with pytest.raises(ValueError):
        configure({"x": "explode"})


# frob:tests python/sadi/store/failpoints.py::failpoint
def test_kill_exits_137(monkeypatch: pytest.MonkeyPatch) -> None:
    """kill calls os._exit(137) without cleanup."""
    codes: list[int] = []
    monkeypatch.setattr(failpoints.os, "_exit", codes.append)
    configure({"k": "kill"})
    failpoint("k")
    assert codes == [137]
