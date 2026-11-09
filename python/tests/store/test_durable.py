"""Tests for the durability primitives: happy paths, fault injection and Windows sharing retry."""

from __future__ import annotations

import errno
import os
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from typani import Err, Ok

from sadi.store import durable, failpoints
from sadi.store.durable import (
    DurableCrossDevice,
    DurableExists,
    DurableIo,
    DurableSharingViolation,
    atomic_replace,
    create_exclusive,
    fsync_dir,
    fsync_file,
    rename_noreplace,
)


@pytest.fixture(autouse=True)
def _reset(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear failpoints and make retry sleeps instant and the clock controllable."""
    failpoints.clear()
    monkeypatch.setattr(durable, "_sleep", lambda _s: None)
    yield
    failpoints.clear()


def _write(path: Path, data: bytes) -> None:
    """Write a small file."""
    path.write_bytes(data)


# frob:tests python/sadi/store/durable.py::fsync_file
def test_fsync_file_ok(tmp_path: Path) -> None:
    """fsync_file succeeds on a written fd."""
    fd = os.open(tmp_path / "f", os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0))
    try:
        os.write(fd, b"x")
        assert fsync_file(fd) == Ok(None)
    finally:
        os.close(fd)


# frob:tests python/sadi/store/durable.py::fsync_file
def test_fsync_file_error_is_result(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A failing os.fsync becomes Err(DurableIo), not an exception."""

    def boom(_fd: int) -> None:
        raise OSError(errno.EIO, "eio")

    # Patch the platform-neutral flush: macOS uses F_FULLFSYNC, not os.fsync.
    monkeypatch.setattr(durable, "_flush_fd", boom)
    fd = os.open(tmp_path / "f", os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0))
    try:
        r = fsync_file(fd)
    finally:
        os.close(fd)
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableIo)
    assert r.danger_err.errno == errno.EIO


# frob:tests python/sadi/store/durable.py::fsync_file
def test_fsync_failpoint_injection(tmp_path: Path) -> None:
    """The durable.fsync_file failpoint injects ENOSPC."""
    failpoints.configure({"durable.fsync_file": "error:28"})
    fd = os.open(tmp_path / "f", os.O_WRONLY | os.O_CREAT | getattr(os, "O_BINARY", 0))
    try:
        r = fsync_file(fd)
    finally:
        os.close(fd)
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableIo)
    assert r.danger_err.errno == errno.ENOSPC


# frob:tests python/sadi/store/durable.py::fsync_dir
@pytest.mark.skipif(sys.platform == "win32", reason="fsync_dir is a no-op on Windows")
def test_fsync_dir_ok_and_missing(tmp_path: Path) -> None:
    """fsync_dir flushes a real directory and reports a missing one as Err."""
    assert fsync_dir(tmp_path) == Ok(None)
    r = fsync_dir(tmp_path / "nope")
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableIo)


# frob:tests python/sadi/store/durable.py::durability_downgraded
def test_durability_downgraded_default() -> None:
    """No downgrade is reported unless F_FULLFSYNC fell back."""
    assert durable.durability_downgraded() is False


# frob:tests python/sadi/store/durable.py::fsync_dir
def test_fsync_dir_windows_flushes_via_ctypes_helper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """On Windows fsync_dir delegates to the ctypes flush and maps its failure to Err."""
    calls: list[Path] = []
    monkeypatch.setattr(durable, "_IS_WIN", True)
    monkeypatch.setattr(durable, "_win_flush_dir", calls.append)
    assert fsync_dir(tmp_path) == Ok(None)
    assert calls == [tmp_path]

    def _boom(_p: Path) -> None:
        raise OSError(errno.EIO, "flush failed")

    monkeypatch.setattr(durable, "_win_flush_dir", _boom)
    r = fsync_dir(tmp_path)
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableIo)
    assert r.danger_err.errno == errno.EIO


# frob:tests python/sadi/store/durable.py::rename_noreplace
def test_rename_noreplace_moves_and_refuses_overwrite(tmp_path: Path) -> None:
    """A free destination receives the file; an existing one is untouched and DurableExists."""
    src, dst = tmp_path / "a", tmp_path / "b"
    _write(src, b"new")
    assert rename_noreplace(src, dst) == Ok(None)
    assert dst.read_bytes() == b"new"
    assert not src.exists()
    _write(src, b"other")
    r = rename_noreplace(src, dst)
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableExists)
    assert dst.read_bytes() == b"new"
    assert src.read_bytes() == b"other"


# frob:tests python/sadi/store/durable.py::rename_noreplace
def test_rename_noreplace_link_fallback(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """The link+unlink fallback (macOS path) moves, and refuses to overwrite."""
    monkeypatch.setattr(durable, "_IS_WIN", False)
    monkeypatch.setattr(sys, "platform", "darwin")
    src, dst = tmp_path / "a", tmp_path / "b"
    _write(src, b"x")
    assert rename_noreplace(src, dst) == Ok(None)
    assert dst.read_bytes() == b"x"
    _write(src, b"y")
    r = rename_noreplace(src, dst)
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableExists)
    assert dst.read_bytes() == b"x"


# frob:tests python/sadi/store/durable.py::rename_noreplace
def test_rename_noreplace_renameat2_unsupported_falls_back(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """When renameat2 reports unsupported the link+unlink fallback is used."""
    monkeypatch.setattr(durable, "_renameat2_noreplace", lambda _s, _d: False)
    src, dst = tmp_path / "a", tmp_path / "b"
    _write(src, b"x")
    monkeypatch.setattr(sys, "platform", "linux")
    assert rename_noreplace(src, dst) == Ok(None)
    assert dst.read_bytes() == b"x"


# frob:tests python/sadi/store/durable.py::rename_noreplace
def test_rename_noreplace_missing_source(tmp_path: Path) -> None:
    """A missing source is a DurableIo error and creates nothing."""
    r = rename_noreplace(tmp_path / "nope", tmp_path / "dst")
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableIo)
    assert not (tmp_path / "dst").exists()


class _FakeMove:
    """Stand-in for kernel32.MoveFileExW recording flags and returning a canned result."""

    def __init__(self, ok: bool) -> None:
        self.ok = ok
        self.flags: list[int] = []

    def __call__(self, _s: str, _d: str, flags: int) -> int:
        self.flags.append(flags)
        return 1 if self.ok else 0


# frob:tests python/sadi/store/durable.py::rename_noreplace
@pytest.mark.parametrize("code", [80, 183])
def test_rename_noreplace_windows_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, code: int
) -> None:
    """Windows ALREADY_EXISTS/FILE_EXISTS map to DurableExists; REPLACE_EXISTING is never set."""
    fake = _FakeMove(ok=False)
    monkeypatch.setattr(durable, "_IS_WIN", True)
    monkeypatch.setattr(
        durable.ctypes,
        "windll",
        type("W", (), {"kernel32": type("K", (), {"MoveFileExW": fake})}),
        raising=False,
    )
    monkeypatch.setattr(durable.ctypes, "get_last_error", lambda: code, raising=False)
    monkeypatch.setattr(durable, "fsync_dir", lambda _p: Ok(None))
    r = rename_noreplace(tmp_path / "a", tmp_path / "b")
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableExists)
    assert fake.flags == [durable._MOVEFILE_WRITE_THROUGH]
    assert not fake.flags[0] & durable._MOVEFILE_REPLACE_EXISTING


# frob:tests python/sadi/store/durable.py::rename_noreplace
def test_rename_noreplace_windows_success(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Windows success path calls MoveFileExW once and flushes the directory."""
    fake = _FakeMove(ok=True)
    synced: list[Path] = []
    monkeypatch.setattr(durable, "_IS_WIN", True)
    monkeypatch.setattr(
        durable.ctypes,
        "windll",
        type("W", (), {"kernel32": type("K", (), {"MoveFileExW": fake})}),
        raising=False,
    )
    monkeypatch.setattr(durable, "fsync_dir", lambda p: (synced.append(p), Ok(None))[1])
    assert rename_noreplace(tmp_path / "a", tmp_path / "b") == Ok(None)
    assert len(fake.flags) == 1
    assert synced == [tmp_path]


# frob:tests python/sadi/store/durable.py::create_exclusive
def test_create_exclusive_never_overwrites(tmp_path: Path) -> None:
    """A second exclusive create fails with DurableExists and leaves content intact."""
    p = tmp_path / "seg"
    r = create_exclusive(p)
    assert isinstance(r, Ok)
    os.write(r.danger_ok, b"keep")
    os.close(r.danger_ok)
    r2 = create_exclusive(p)
    assert isinstance(r2, Err)
    assert isinstance(r2.danger_err, DurableExists)
    assert p.read_bytes() == b"keep"


# frob:tests python/sadi/store/durable.py::atomic_replace
def test_atomic_replace_ok(tmp_path: Path) -> None:
    """Replace swaps content and removes the tmp file."""
    dst, tmp = tmp_path / "m.json", tmp_path / ".m.tmp"
    _write(dst, b"old")
    _write(tmp, b"new")
    assert atomic_replace(tmp, dst) == Ok(None)
    assert dst.read_bytes() == b"new"
    assert not tmp.exists()


# frob:tests python/sadi/store/durable.py::atomic_replace
def test_atomic_replace_fsync_failure_keeps_original(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If the data fsync fails the original is untouched and no rename happens."""
    dst, tmp = tmp_path / "m.json", tmp_path / ".m.tmp"
    _write(dst, b"old")
    _write(tmp, b"new")

    def boom(_fd: int) -> None:
        raise OSError(errno.EIO, "eio")

    monkeypatch.setattr(durable, "_flush_fd", boom)
    r = atomic_replace(tmp, dst)
    assert isinstance(r, Err)
    assert dst.read_bytes() == b"old"
    assert tmp.exists()


# frob:tests python/sadi/store/durable.py::atomic_replace
def test_atomic_replace_rename_failure_keeps_original(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """If os.replace fails the original is intact."""
    dst, tmp = tmp_path / "m.json", tmp_path / ".m.tmp"
    _write(dst, b"old")
    _write(tmp, b"new")

    def boom(_a: object, _b: object) -> None:
        raise OSError(errno.EIO, "eio")

    monkeypatch.setattr(durable, "_IS_WIN", False)
    monkeypatch.setattr(durable.os, "replace", boom)
    r = atomic_replace(tmp, dst)
    assert isinstance(r, Err)
    assert dst.read_bytes() == b"old"


# frob:tests python/sadi/store/durable.py::atomic_replace
def test_atomic_replace_rename_failpoint(tmp_path: Path) -> None:
    """The durable.rename failpoint fails the replace and leaves dst intact."""
    dst, tmp = tmp_path / "m.json", tmp_path / ".m.tmp"
    _write(dst, b"old")
    _write(tmp, b"new")
    failpoints.configure({"durable.rename": "error:5"})
    assert isinstance(atomic_replace(tmp, dst), Err)
    assert dst.read_bytes() == b"old"


# frob:tests python/sadi/store/durable.py::atomic_replace
def test_atomic_replace_dir_fsync_failure_reported(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A dir-fsync failure after the rename is surfaced loudly (I9)."""
    dst, tmp = tmp_path / "m.json", tmp_path / ".m.tmp"
    _write(tmp, b"new")
    monkeypatch.setattr(durable, "fsync_dir", lambda _p: Err(DurableIo(errno=errno.EIO)))
    assert isinstance(atomic_replace(tmp, dst), Err)


# frob:tests python/sadi/store/durable.py::atomic_replace
def test_atomic_replace_cross_dir(tmp_path: Path) -> None:
    """tmp in another directory is rejected before any I/O."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    _write(tmp_path / "a" / "t", b"n")
    r = atomic_replace(tmp_path / "a" / "t", tmp_path / "b" / "d")
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableCrossDevice)


class _WinPermissionError(PermissionError):
    """PermissionError with the Windows-only `winerror` attribute."""

    winerror: int = 0


def _sharing_error(code: int) -> PermissionError:
    """Build a PermissionError carrying a Windows winerror attribute."""
    exc = _WinPermissionError(13, "sharing")
    exc.winerror = code
    return exc


# frob:tests python/sadi/store/durable.py::atomic_replace
def test_sharing_violation_retried_then_succeeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Two sharing violations are retried with doubling backoff, then the replace succeeds."""
    dst, tmp = tmp_path / "m.json", tmp_path / ".m.tmp"
    _write(tmp, b"new")
    real = durable._replace_os
    calls = {"n": 0}
    sleeps: list[float] = []

    def flaky(a: Path, b: Path) -> None:
        calls["n"] += 1
        if calls["n"] <= 2:
            raise _sharing_error(32)
        real(a, b)

    monkeypatch.setattr(durable, "_replace_os", flaky)
    monkeypatch.setattr(durable, "_sleep", sleeps.append)
    assert atomic_replace(tmp, dst) == Ok(None)
    assert sleeps == [0.01, 0.02]
    assert dst.read_bytes() == b"new"


# frob:tests python/sadi/store/durable.py::atomic_replace
def test_sharing_violation_gives_up(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A persistent sharing violation ends in DurableSharingViolation, dst intact."""
    dst, tmp = tmp_path / "m.json", tmp_path / ".m.tmp"
    _write(dst, b"old")
    _write(tmp, b"new")
    clock = {"t": 0.0}

    def always(_a: Path, _b: Path) -> None:
        raise _sharing_error(5)

    monkeypatch.setattr(durable, "_replace_os", always)
    monkeypatch.setattr(durable, "_monotonic", lambda: clock["t"])
    monkeypatch.setattr(durable, "_sleep", lambda s: clock.__setitem__("t", clock["t"] + s))
    r = atomic_replace(tmp, dst)
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableSharingViolation)
    assert r.danger_err.attempts > 3
    assert dst.read_bytes() == b"old"


# frob:tests python/sadi/store/durable.py::create_exclusive
def test_plain_permission_error_not_retried(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A PermissionError without a sharing winerror fails at once."""
    sleeps: list[float] = []
    monkeypatch.setattr(durable, "_sleep", sleeps.append)

    def deny(*_a: object, **_k: object) -> int:
        raise PermissionError(errno.EACCES, "denied")

    monkeypatch.setattr(durable.os, "open", deny)
    r = create_exclusive(tmp_path / "x")
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableIo)
    assert sleeps == []


# frob:tests python/sadi/store/durable.py::atomic_replace
@pytest.mark.skipif(sys.platform != "win32", reason="needs a real exclusive Windows handle")
def test_windows_held_handle_sharing_violation(tmp_path: Path) -> None:
    """A real handle opened with share mode 0 makes replace fail with SharingViolation."""
    import ctypes  # noqa: PLC0415

    dst, tmp = tmp_path / "m.json", tmp_path / ".m.tmp"
    _write(dst, b"old")
    _write(tmp, b"new")
    k32 = ctypes.windll.kernel32  # ty: ignore[unresolved-attribute]
    k32.CreateFileW.restype = ctypes.c_void_p
    handle = k32.CreateFileW(str(dst), 0x80000000, 0, None, 3, 0x80, None)
    assert handle not in (None, ctypes.c_void_p(-1).value)
    try:
        durable.SHARING_RETRY_TOTAL_S = 0.2  # keep the test fast
        r = atomic_replace(tmp, dst)
    finally:
        k32.CloseHandle(ctypes.c_void_p(handle))
        durable.SHARING_RETRY_TOTAL_S = 5.0
    assert isinstance(r, Err)
    assert isinstance(r.danger_err, DurableSharingViolation)
