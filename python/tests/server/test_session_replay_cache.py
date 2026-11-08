"""Shared SessionReplayCache: plots/export/curve events equal a full replay, with fallback."""

# frob:ticket 01M6X8XTQ31XRDC5BZFNQZXN6Q
from __future__ import annotations

import uuid
from pathlib import Path

from sadi.server.curve_source import SessionReplayCache, make_curve_source, session_events
from sadi.store.events import PointV1, PointWindow, point_record
from sadi.store.session import SessionMeta, create_session
from sadi.store.writer_thread import WriterHandle


def _load(i: int) -> PointV1:
    """Build a load POINT with distinguishable volts."""
    return PointV1(
        phase="load",
        window=PointWindow(first_raw_seq=1, last_raw_seq=1),
        inputs={"volts": 0.1 * i, "mass_kg": float(i)},
    )


def _session(root: Path, n: int) -> tuple[Path, WriterHandle]:
    """Create a session with `n` points; the writer stays open for more appends."""
    h = create_session(root, SessionMeta(slug="rc")).danger_ok
    w = WriterHandle.open(h.path / "wal", uuid.uuid4(), 1).danger_ok
    for i in range(1, n + 1):
        assert w.submit(point_record(_load(i))).is_ok
    return h.path, w


# frob:tests python/sadi/server/curve_source.py::SessionReplayCache.events
def test_cached_events_equal_full_replay_as_wal_grows(tmp_path: Path) -> None:
    """Repeated cached calls while points are appended equal a fresh full replay each time."""
    sdir, w = _session(tmp_path, 2)
    assert w.wait_durable(2, 10.0).is_ok
    cache = SessionReplayCache()
    assert cache.events(sdir).danger_ok == session_events(sdir).danger_ok
    for i in range(3, 6):
        last = w.submit(point_record(_load(i))).danger_ok
        assert w.wait_durable(last, 10.0).is_ok
        assert cache.events(sdir).danger_ok == session_events(sdir).danger_ok
    assert w.close().is_ok


# frob:tests python/sadi/server/curve_source.py::SessionReplayCache.events
def test_corruption_falls_back_to_full_replay_error(tmp_path: Path) -> None:
    """Mid-log corruption yields the same Err as the full replay, never stale cached data."""
    sdir, w = _session(tmp_path, 3)
    assert w.wait_durable(3, 10.0).is_ok
    cache = SessionReplayCache()
    assert cache.events(sdir).is_ok
    for i in range(4, 20):
        assert w.submit(point_record(_load(i))).is_ok
    assert w.close().is_ok
    seg = next((sdir / "wal").glob("seg-*.wal"))
    data = bytearray(seg.read_bytes())
    data[len(data) // 2] ^= 0xFF  # inside the not-yet-applied tail
    seg.write_bytes(bytes(data))
    full = session_events(sdir)
    assert full.is_err
    got = cache.events(sdir)
    assert got.is_err and got.danger_err == full.danger_err
    assert SessionReplayCache().events(sdir).is_err


# frob:tests python/sadi/server/curve_source.py::SessionReplayCache.curve
# frob:tests python/sadi/server/curve_source.py::make_curve_source
def test_curve_source_shares_the_cache(tmp_path: Path) -> None:
    """A curve source built on a shared cache reuses the replayer the events path created."""
    sdir, w = _session(tmp_path, 3)
    assert w.close().is_ok
    cache = SessionReplayCache()
    assert cache.events(sdir).is_ok
    before = dict(cache._cache)  # noqa: SLF001
    make_curve_source(tmp_path, cache)()
    assert cache._cache == before  # noqa: SLF001


# frob:tests python/sadi/server/curve_source.py::SessionReplayCache.events
def test_cache_is_bounded(tmp_path: Path) -> None:
    """Only a handful of session replayers stay cached."""
    cache = SessionReplayCache()
    for i in range(8):
        d = tmp_path / f"s{i}"
        (d / "wal").mkdir(parents=True)
        cache.events(d)
    assert len(cache._cache) <= 4  # noqa: SLF001
