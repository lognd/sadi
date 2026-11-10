"""A failed writer must spill its undurable records on close, never drop them."""

# frob:ticket 01M726PZKE3CYNC5NABZC56HT2
from __future__ import annotations

from pathlib import Path

import pytest
from typani import Err, Result

from sadi.core.registry import LabRegistry
from sadi.labs.lctt.plugin import register
from sadi.server.schemas import SessionCreate
from sadi.server.service import SessionService
from sadi.store.records import Record, RecordType
from sadi.store.spill import import_all_spills, user_data_dir
from sadi.store.writer_thread import IoError, WriterError, WriterHandle


class _FailedWriter:
    """Delegates to a real writer but reports FAILED on close with fixed undurable records."""

    def __init__(self, real: WriterHandle, records: list[Record], fail_closes: int) -> None:
        self._real = real
        self._records = records
        self._fails = fail_closes

    def close(self) -> Result[None, WriterError]:
        if self._fails > 0:
            self._fails -= 1
            return Err(IoError(reason="injected EIO", errno=5))
        self._real.close()
        return Err(IoError(reason="injected EIO", errno=5))

    def undurable_records(self) -> list[Record]:
        return list(self._records)

    def __getattr__(self, name: str) -> object:
        return getattr(self._real, name)


def _records() -> list[Record]:
    return [
        Record(
            type=int(RecordType.NOTE),
            seq=seq,
            wall_ns=seq,
            flags=0,
            payload=f"p{seq}".encode(),
            crc=0,
        )
        for seq in (5, 6, 7)
    ]


def _service(tmp_path: Path, fail_closes: int) -> SessionService:
    labs = LabRegistry()
    assert labs.register(register()).is_ok
    svc = SessionService(tmp_path, labs, synthetic=True)
    assert svc.create(SessionCreate(lab="lctt", slug="s")).is_ok
    cur = svc._open
    assert cur is not None
    cur.writer = _FailedWriter(cur.writer, _records(), fail_closes)  # type: ignore[assignment]
    return svc


# frob:tests python/sadi/server/service.py::SessionService.close
# frob:tests python/sadi/store/spill.py::write_spill
# frob:tests python/sadi/store/writer_thread.py::WriterHandle.undurable_records
def test_failed_close_spills_and_import_recovers(
    tmp_path: Path, isolated_spill_dirs: tuple[Path, Path]
) -> None:
    svc = _service(tmp_path, fail_closes=0)
    res = svc.close()
    assert res.is_err
    assert svc._open is None
    spills = list((tmp_path / "spill").glob("*.wal"))
    assert len(spills) == 1
    assert not list((tmp_path / "spill").glob(".*"))
    out = import_all_spills(tmp_path, *isolated_spill_dirs)
    assert len(out) == 1
    imported = out[0][1]
    assert imported.is_ok
    report = imported.danger_ok
    assert report is not None
    assert (report.record_count, report.first_seq, report.last_seq) == (3, 5, 7)
    assert spills[0].exists()


# frob:tests python/sadi/server/service.py::SessionService.close
# frob:tests python/sadi/server/service.py::SessionService.shutdown
def test_spill_failure_returns_409_and_keeps_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    svc = _service(tmp_path, fail_closes=1)
    blocker = tmp_path / "blocked"
    blocker.write_text("x")
    (tmp_path / "spill").write_text("x")  # data-root/spill cannot be a directory
    monkeypatch.setenv("XDG_DATA_HOME", str(blocker))
    monkeypatch.setattr("tempfile.tempdir", str(blocker))
    assert user_data_dir().parent == blocker
    res = svc.close()
    assert res.is_err
    assert res.danger_err.status == 409
    assert svc._open is not None  # records still held in memory
    svc.shutdown()  # logged, never raised, still retained
    assert svc._open is not None
    # operator fixes the disk and retries
    (tmp_path / "spill").unlink()
    retry = svc.close()
    assert retry.is_err
    assert svc._open is None
    assert len(list((tmp_path / "spill").glob("*.wal"))) == 1
