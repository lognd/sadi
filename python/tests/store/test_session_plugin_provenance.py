"""Tests for plugin provenance in the session manifest and non-fatal reopen warnings."""

# frob:ticket 01M6WFZFBK0KYAGBM1CD5GGH60
from __future__ import annotations

import json
import uuid
from pathlib import Path

from sadi.store.manifest import MANIFEST_NAME, SessionPluginRef, read_manifest
from sadi.store.records import NewRecord, RecordType
from sadi.store.session import SessionMeta, create_session, open_readonly, resume_session
from sadi.store.wal import WalConfig, WalWriter

REF = SessionPluginRef(id="lctt", version="1.2.0")


def _make(tmp_path: Path) -> Path:
    h = create_session(tmp_path, SessionMeta(plugins=(REF,))).danger_ok
    path = h.path
    w = WalWriter.open(path / "wal", uuid.UUID(h.manifest.session_uuid), 1, WalConfig()).danger_ok
    assert w.append(NewRecord(type=int(RecordType.NOTE), payload=b"x" * 9)).is_ok
    w.close()
    assert h.close().is_ok
    return path


# frob:tests python/sadi/store/session.py::create_session
def test_new_manifest_records_plugin(tmp_path: Path) -> None:
    """New session manifest contains plugin id and version."""
    mf = read_manifest(_make(tmp_path)).danger_ok
    assert mf is not None
    assert mf.plugins == (REF,)


# frob:tests python/sadi/store/session.py::open_readonly
def test_old_manifest_without_field_reopens(tmp_path: Path) -> None:
    """A manifest lacking the plugins key still validates and opens."""
    path = _make(tmp_path)
    f = path / MANIFEST_NAME
    data = json.loads(f.read_text())
    del data["plugins"]
    f.write_text(json.dumps(data))
    ro = open_readonly(path, {}).danger_ok
    assert ro.manifest is not None
    assert ro.manifest.plugins == ()
    assert ro.plugin_warnings == ()


# frob:tests python/sadi/store/session.py::open_readonly
def test_missing_plugin_warns_not_fails(tmp_path: Path) -> None:
    """Reopen with the plugin absent succeeds with a warning naming it."""
    ro = open_readonly(_make(tmp_path), {}).danger_ok
    assert len(ro.plugin_warnings) == 1
    assert "lctt" in ro.plugin_warnings[0].message


# frob:tests python/sadi/store/manifest.py::plugin_warnings
def test_version_differs_warns_and_match_is_silent(tmp_path: Path) -> None:
    """A different version warns; an identical one does not."""
    path = _make(tmp_path)
    assert (
        open_readonly(path, {"lctt": "2.0.0"}).danger_ok.plugin_warnings[0].found_version == "2.0.0"
    )
    assert open_readonly(path, {"lctt": "1.2.0"}).danger_ok.plugin_warnings == ()
    assert open_readonly(path).danger_ok.plugin_warnings == ()


# frob:tests python/sadi/store/session.py::resume_session
def test_resume_inherits_or_overrides(tmp_path: Path) -> None:
    """Resume keeps parent plugins unless new ones are given."""
    parent = _make(tmp_path)
    h = resume_session(parent).danger_ok
    assert h.manifest.plugins == (REF,)
    assert h.close().is_ok
    new = SessionPluginRef(id="x", version="0.1")
    h2 = resume_session(parent, plugins=[new]).danger_ok
    assert h2.manifest.plugins == (new,)
    assert h2.close().is_ok
