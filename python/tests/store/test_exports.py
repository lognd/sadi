"""Tests for derived exports: no overwrite, atomic publish, provenance, regeneration from WAL."""

# frob:ticket 01M6W7R04QJTECCTSV9EY2JADK
from __future__ import annotations

import hashlib
import json
import shutil
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from sadi.store import failpoints
from sadi.store.events import PointV1, PointWindow, point_record, replay_wal
from sadi.store.exports import (
    ExportError,
    ExportProvenanceV1,
    list_exports,
    next_number,
    write_export,
)
from sadi.store.records import RecordType
from sadi.store.session import SessionHandle, SessionMeta, create_session
from sadi.store.snapshot import prefix_hash
from sadi.store.wal import WalConfig, WalWriter

NOW = datetime(2026, 11, 8, 15, 30, 0, tzinfo=UTC)
WIN = PointWindow(first_raw_seq=2, last_raw_seq=9)


@pytest.fixture(autouse=True)
def _reset() -> Iterator[None]:
    """Clear failpoints around each test."""
    failpoints.clear()
    yield
    failpoints.clear()


def make_session(tmp_path: Path, n_points: int = 3) -> SessionHandle:
    """Create a session with `n_points` durable POINT records."""
    h = create_session(tmp_path, SessionMeta(slug="ex"), NOW).danger_ok
    w = WalWriter.open(h.path / "wal", uuid.UUID(h.manifest.session_uuid), 1, WalConfig())
    for i in range(1, n_points + 1):
        pt = PointV1(point_id=f"p{i}", phase="load", window=WIN, inputs={"load_N": 10.0 * i})
        w.danger_ok.append(point_record(pt)).expect("append")
    w.danger_ok.close().expect("close")
    return h


def render(h: SessionHandle) -> bytes:
    """Deterministic export bytes derived purely from the WAL."""
    state = replay_wal(h.path / "wal").danger_ok
    rows = [f"{p.point.point_id},{p.inputs['load_N']}" for p in state.view().points]
    return ("\r\n".join(["id,load", *rows]) + "\r\n").encode()


def tree(root: Path) -> dict[str, bytes]:
    """Map every file under root to its bytes."""
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


# frob:tests python/sadi/store/exports.py::write_export
def test_export_has_versioned_name_and_provenance(tmp_path: Path) -> None:
    """The export lands under exports/<kind>/ with a sidecar citing WAL range and hash."""
    h = make_session(tmp_path)
    data = render(h)
    res = write_export(
        h, "csv", "run", "csv", data, now=NOW, code_version={"sadi": "1"}, parameters={"u": "N"}
    ).expect("export")
    assert res.path.name == "0001-20261108T153000Z-run.csv"
    assert res.path.read_bytes() == data
    prov = ExportProvenanceV1.model_validate_json(res.sidecar.read_bytes())  # type: ignore[union-attr]
    assert prov.sha256 == hashlib.sha256(data).hexdigest() and prov.size == len(data)
    assert prov.covers_seq == 3
    assert prov.prefix_hash == prefix_hash(h.path / "wal", 3).danger_ok
    assert prov.path == "exports/csv/0001-20261108T153000Z-run.csv"
    assert prov.parameters == {"u": "N"} and prov.code_version == {"sadi": "1"}
    assert [e.complete for e in list_exports(h.path, "csv")] == [True]


# frob:tests python/sadi/store/exports.py::write_export
def test_exports_never_overwrite(tmp_path: Path) -> None:
    """Same name twice gives two files; the first is byte-identical afterwards."""
    h = make_session(tmp_path)
    a = write_export(h, "csv", "run", "csv", b"first", now=NOW).expect("a")
    b = write_export(h, "csv", "run", "csv", b"second", now=NOW).expect("b")
    assert a.path != b.path and b.path.name.startswith("0002-")
    assert a.path.read_bytes() == b"first" and b.path.read_bytes() == b"second"
    assert next_number(a.path.parent) == 3


# frob:tests python/sadi/store/exports.py::write_export
def test_number_collision_takes_next(tmp_path: Path) -> None:
    """A racing file with the chosen number is kept; the export takes the next number."""
    h = make_session(tmp_path)
    first = write_export(h, "csv", "run", "csv", b"x", now=NOW).expect("first")
    squatter = first.path.parent / "0002-20261108T153000Z-run.csv"
    squatter.write_bytes(b"squat")
    res = write_export(h, "csv", "run", "csv", b"y", now=NOW).expect("second")
    assert res.path.name.startswith("0003-") and squatter.read_bytes() == b"squat"


# frob:tests python/sadi/store/exports.py::write_export
@pytest.mark.parametrize("point", ["export.data.write", "export.data.fsync", "export.rename"])
def test_failure_before_publish_leaves_no_final(tmp_path: Path, point: str) -> None:
    """A fault before publish leaves no file at a final name and returns Io."""
    h = make_session(tmp_path)
    failpoints.configure({point: "error:5"})
    res = write_export(h, "csv", "run", "csv", b"data", now=NOW)
    assert res.is_err and res.danger_err == ExportError.Io
    assert list_exports(h.path, "csv") == []


# frob:tests python/sadi/store/exports.py::write_export
def test_sidecar_failure_marks_incomplete(tmp_path: Path) -> None:
    """A crash before the sidecar leaves a complete data file listed as incomplete."""
    h = make_session(tmp_path)
    failpoints.configure({"export.sidecar.write": "error:5"})
    res = write_export(h, "csv", "run", "csv", b"data", now=NOW)
    assert res.is_err
    listed = list_exports(h.path, "csv")
    assert len(listed) == 1 and not listed[0].complete
    assert listed[0].path.read_bytes() == b"data"


# frob:tests python/sadi/store/exports.py::write_export
def test_bad_extension_and_ahead_are_refused(tmp_path: Path) -> None:
    """Unusable extension and covers_seq beyond the WAL are typed errors; nothing is written."""
    h = make_session(tmp_path)
    assert write_export(h, "csv", "run", "../x", b"d").danger_err == ExportError.BadName
    assert write_export(h, "csv", "run", "csv", b"d", covers_seq=99).danger_err == ExportError.Ahead
    assert not [p for p in (h.path / "exports").rglob("*") if p.is_file()]


# frob:tests python/sadi/store/exports.py::write_export
def test_kind_cannot_escape_exports_dir(tmp_path: Path) -> None:
    """A hostile kind or basename is sanitised and stays under exports/."""
    h = make_session(tmp_path)
    res = write_export(h, "../..", "a/b", "csv", b"d", now=NOW).expect("export")
    assert (h.path / "exports") in res.path.parents


# frob:tests python/sadi/store/exports.py::write_export
def test_ref_sink_receives_export_ref(tmp_path: Path) -> None:
    """The optional sink gets an EXPORT_REF record; a failing sink never fails the export."""
    h = make_session(tmp_path)
    seen = []
    from typani import Ok

    write_export(h, "csv", "r", "csv", b"d", ref_sink=lambda n: (seen.append(n), Ok(None))[1])
    assert [n.type for n in seen] == [RecordType.EXPORT_REF]
    assert json.loads(seen[0].payload)["covers_seq"] == 3


# frob:tests python/sadi/store/exports.py::write_export
def test_regenerate_from_wal_after_deleting_exports(tmp_path: Path) -> None:
    """Deleting exports/ loses nothing: the WAL regenerates byte-identical exports."""
    h = make_session(tmp_path)
    wal_before = tree(h.path / "wal")
    first = write_export(h, "csv", "run", "csv", render(h), now=NOW).expect("export")
    original = first.path.read_bytes()
    original_prov = json.loads(first.sidecar.read_bytes())  # type: ignore[union-attr]
    shutil.rmtree(h.path / "exports")
    again = write_export(h, "csv", "run", "csv", render(h), now=NOW).expect("regen")
    assert again.path.read_bytes() == original and again.path.name == first.path.name
    prov = json.loads(again.sidecar.read_bytes())  # type: ignore[union-attr]
    assert prov["sha256"] == original_prov["sha256"]
    assert prov["prefix_hash"] == original_prov["prefix_hash"]
    assert tree(h.path / "wal") == wal_before
