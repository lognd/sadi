"""capture() must block until the scope reports DONE (real AD3 passes through PREFILL/ARMED)."""

# frob:ticket 01M6Z4EQZNMV31NM299XC9RPS4
from __future__ import annotations

from typing import Any, cast

from typani import Err, Ok

from sadi.bench.ad3.backend import DwfBackend, DwfCode
from sadi.bench.ad3.consts import AcqState
from sadi.bench.inject import capture
from tests.e2e.ad3_flow import make_fake


class _SlowFake:
    """Delegates to a FakeDwf but reports PREFILL then ARMED for the first status polls."""

    def __init__(self, inner: Any, pending: int) -> None:
        self._inner = inner
        self.pending = pending
        self.polls = 0

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)

    def in_status(self, dev: Any, read_data: bool) -> Any:
        self.polls += 1
        if self.pending > 0:
            self.pending -= 1
            return Ok(AcqState.PREFILL if self.pending % 2 else AcqState.ARMED)
        return self._inner.in_status(dev, read_data)


class _NeverDone(_SlowFake):
    def in_status(self, dev: Any, read_data: bool) -> Any:
        return Ok(AcqState.PREFILL)


# frob:tests python/sadi/bench/inject.py::capture
def test_capture_waits_through_prefill_and_armed() -> None:
    """Capture polls past PREFILL/ARMED and then returns the full sample count."""
    slow = _SlowFake(make_fake(), pending=5)
    dev = slow.open(0).danger_ok
    res = capture(cast(DwfBackend, slow), dev, 0, 1000.0, 50)
    slow.close(dev)
    assert isinstance(res, Ok) and len(res.unwrap()) == 50
    assert slow.polls > 5


# frob:tests python/sadi/bench/inject.py::capture
def test_capture_times_out_when_never_done(monkeypatch: Any) -> None:
    """A scope stuck in PREFILL yields Err(TIMEOUT) rather than a short read."""
    monkeypatch.setattr("sadi.bench.inject._CAPTURE_MARGIN_S", 0.05)
    stuck = _NeverDone(make_fake(), pending=0)
    dev = stuck.open(0).danger_ok
    res = capture(cast(DwfBackend, stuck), dev, 0, 1000.0, 10)
    stuck.close(dev)
    assert isinstance(res, Err) and res.unwrap_err().code == DwfCode.TIMEOUT
