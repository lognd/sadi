"""The server writes atomic, recoverable snapshots of live sessions (data-safety.md 9.1)."""

# frob:ticket 01M71YY12XP2ZDM402A00A7RJW

from __future__ import annotations

from pathlib import Path

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.schemas import CaptureBody, SessionCreate
from sadi.server.service import SessionService
from sadi.store.snapshot import SnapshotCadence, list_snapshots, load_latest_snapshot

WINDOW = {"first_raw_seq": 1, "last_raw_seq": 5}


def _service(root: Path) -> SessionService:
    """Service over `root` with the lctt lab registered."""
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    return SessionService(root, labs)


# frob:tests python/sadi/server/service.py::SessionService._snapshot
def test_capture_and_close_write_snapshots_recoverable_without_close(tmp_path: Path) -> None:
    """A point snapshots at once (loadable mid-session, as after SIGKILL); close adds one more."""
    svc = _service(tmp_path)
    info = svc.create(SessionCreate(lab="lctt", slug="sn")).danger_ok
    sdir = tmp_path / "sessions" / info.name
    body = CaptureBody.model_validate(
        {"phase": "calibration", "inputs": {"volts": 1.0, "height": 0.01}, "window": WINDOW}
    )
    assert svc.skip("setup").is_ok
    assert svc.capture(body).is_ok
    live = load_latest_snapshot(sdir).danger_ok
    assert live is not None and len(live.state["points"]) == 1
    assert svc.capture(body).is_ok
    mid = len(list_snapshots(sdir))
    assert mid >= 2  # never replaced: both kept
    from sadi.store.snapshot import prefix_hash  # noqa: PLC0415

    for _path, snap in list_snapshots(sdir):  # running hash == full-scan hash
        assert prefix_hash(sdir / "wal", snap.covers_seq).danger_ok == snap.prefix_hash
    assert svc.close().is_ok
    final = load_latest_snapshot(sdir).danger_ok
    assert final is not None and len(final.state["points"]) == 2
    assert len(list_snapshots(sdir)) >= mid


# frob:tests python/sadi/store/snapshot.py::SnapshotCadence.due
def test_cadence_rate_limits_unforced_and_dedupes() -> None:
    """Forced always fires (once per seq); unforced waits the interval."""
    now = [0.0]
    c = SnapshotCadence(5.0, clock=lambda: now[0])
    assert c.due(1, False)
    c.written(1)
    assert not c.due(1, True)
    assert c.due(2, True)
    assert not c.due(2, False)
    now[0] = 6.0
    assert c.due(3, False)
