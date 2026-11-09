"""`sadi store`: list, verify, recover and export sessions (data-safety section 5, 8).

Read-only except `recover` (opens a NEW version, the parent is never touched) and `export`
(writes a NEW csv, an existing target is refused). Exit codes are documented in
docs/store/cli.md and exposed as the `Exit` constants below.
"""

# frob:ticket 01M6WEFGAZYBDHQGEG6D2M701Q
# frob:ticket 01M6WEYV1HZCER8M2NVRMF702S
from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict
from typani import Err, Ok, Result, propagate

from sadi.logging_setup import get_logger
from sadi.store.csv_export import write_csv_exclusive
from sadi.store.lock import LockHeld, LockIo, LockStale
from sadi.store.records import FLAG_JSON, RecordType
from sadi.store.session import (
    SESSIONS_DIRNAME,
    Locked,
    NotASession,
    ParentCorrupt,
    ReadOnlySession,
    RootLockFailed,
    SessionError,
    open_readonly,
    probe_lock,
    resume_session,
)
from sadi.store.wal import ScanReport, WalCorrupt, WalReader

_log = get_logger(__name__)

_VERSION_DIR = re.compile(r"^.+\.v\d{3}$")
_EXPORT_HEADER = ("seq", "wall_ns", "type", "payload")


class Exit:
    """Documented process exit codes."""

    OK = 0
    ATTENTION = 1  # readable, but a torn tail, stale manifest or live lock needs a look
    USAGE = 2  # argparse's own code for bad arguments
    CORRUPT = 3  # the WAL is damaged mid-log; nothing was changed
    UNREADABLE = 4  # not a session, no WAL, or an OS error
    REFUSED = 5  # refused to overwrite or to touch a session in use


class CliFailure(BaseModel):
    """A command outcome that is not success: a plain-language message and an exit code."""

    model_config = ConfigDict(frozen=True)
    message: str
    code: int


def _fail(message: str, code: int) -> CliFailure:
    """Build a CliFailure from positional arguments."""
    return CliFailure(message=message, code=code)


def _out(text: str = "") -> None:
    """Write one line of intended CLI output to stdout (the single output helper)."""
    sys.stdout.write(text + "\n")


def _err(text: str) -> None:
    """Write one line of CLI error output to stderr."""
    sys.stderr.write(text + "\n")


def _session_dirs(root: Path) -> list[Path]:
    """Return the `<family>.vNNN` directories under `<root>/sessions`, sorted by name."""
    base = root / SESSIONS_DIRNAME
    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if p.is_dir() and _VERSION_DIR.match(p.name))


def _status(ro: ReadOnlySession) -> tuple[str, int]:
    """Summarise a session as (plain-language status, exit severity)."""
    if ro.scan_error is not None:
        return ("DAMAGED (WAL is corrupt)", Exit.CORRUPT)
    if ro.scan is None:
        return ("incomplete (no WAL)", Exit.ATTENTION)
    if probe_lock(ro.path).is_err:
        return ("in use by another process", Exit.ATTENTION)
    if ro.scan.tail is not None:
        return ("unclean end (torn tail; verified part is intact)", Exit.ATTENTION)
    return ("ok", Exit.OK)


def _open(path: Path) -> Result[ReadOnlySession, CliFailure]:
    """Open a session read-only, mapping failure to a CliFailure."""
    opened = open_readonly(path)
    if opened.is_err:
        err = opened.danger_err
        _log.error("cannot open %s: %s", path, err)
        return Err(_fail(f"{path} is not a session directory.", Exit.UNREADABLE))
    return Ok(opened.danger_ok)


def cmd_list(root: Path) -> Result[int, CliFailure]:
    """List every session under `root` with its status; read-only, exit 0 when listed."""
    dirs = _session_dirs(root)
    if not dirs:
        _out(f"No sessions found under {root / SESSIONS_DIRNAME}.")
        return Ok(Exit.OK)
    for d in dirs:
        opened = open_readonly(d)
        if opened.is_err:
            _out(f"{d.name}: unreadable")
            continue
        ro = opened.danger_ok
        text, _ = _status(ro)
        last = ro.scan.last_seq if ro.scan is not None else None
        recs = ro.scan.record_count if ro.scan is not None else 0
        _out(f"{d.name}: {text}; {recs} records, last seq {last if last is not None else '-'}")
    return Ok(Exit.OK)


def _segment_lines(ro: ReadOnlySession) -> list[str]:
    """Describe the checksum state of every WAL segment, in plain language."""
    lines: list[str] = []
    report: ScanReport | None = ro.scan
    if report is not None:
        for seg in report.segments:
            kind = "sealed, seal hash verified" if seg.sealed else "checksums verified, not sealed"
            span = f"seq {seg.first_seq}-{seg.last_seq}" if seg.last_seq is not None else "empty"
            lines.append(
                f"  segment {seg.segment_no}: OK ({kind}); {seg.record_count} records, {span}"
            )
        if report.tail is not None:
            t = report.tail
            lines.append(
                f"  segment {t.segment}: {t.length} unverified bytes at offset {t.offset} "
                f"({t.reason}); left in place, not used"
            )
        return lines
    err = ro.scan_error
    if isinstance(err, WalCorrupt):
        for p in sorted((ro.path / "wal").glob("seg-*.wal")):
            digits = "".join(c for c in p.stem if c.isdigit())
            no = int(digits) if digits else -1
            if no < err.segment:
                lines.append(f"  segment {no}: OK (checksums verified)")
            elif no == err.segment:
                lines.append(f"  segment {no}: CORRUPT at offset {err.offset}: {err.reason}")
            else:
                lines.append(f"  segment {no}: not checked (after the damage)")
    return lines


@propagate
def cmd_verify(session_dir: Path) -> Result[int, CliFailure]:
    """Verify every WAL checksum and seal of one session; read-only."""
    opened = _open(session_dir)
    ro = opened.unwrap()
    text, sev = _status(ro)
    _out(f"{session_dir.name}: {text}")
    for line in _segment_lines(ro):
        _out(line)
    if ro.scan is not None:
        _out(f"  {ro.scan.record_count} records verified; prefix hash {ro.scan.prefix_hash}")
    if ro.manifest_stale:
        _out("  note: the manifest is missing or out of date (a cache; not repaired here).")
    if ro.scan is None and ro.scan_error is None:
        return Ok(Exit.UNREADABLE)
    return Ok(sev)


def _root_lock_failure(err: RootLockFailed) -> CliFailure:
    """Explain a data-root lock refusal (held, stale or I/O) in plain language."""
    cause = err.error
    if isinstance(cause, LockHeld):
        who = f"pid {cause.pid}" if cause.pid is not None else "another process"
        return _fail(
            f"Refused: the data folder is in use by {who}. Close it and try again.", Exit.REFUSED
        )
    if isinstance(cause, LockStale):
        return _fail(
            f"Refused: a previous sadi process (pid {cause.pid}) exited uncleanly and left "
            "the data folder locked. If it is not running, repeat with `--recover-stale`.",
            Exit.REFUSED,
        )
    if isinstance(cause, LockIo):
        return _fail(f"Could not lock the data folder: {cause.hint}", Exit.UNREADABLE)
    return _fail("Could not lock the data folder.", Exit.UNREADABLE)


def _recover_failure(err: SessionError) -> CliFailure:
    """Translate a resume error into a plain-language CliFailure."""
    if isinstance(err, RootLockFailed):
        return _root_lock_failure(err)
    if isinstance(err, Locked):
        return _fail("Refused: another process has this session open for writing.", Exit.REFUSED)
    if isinstance(err, ParentCorrupt):
        return _fail(
            "Refused: the recording is damaged in the middle. Nothing was changed; "
            "run `verify` for details.",
            Exit.CORRUPT,
        )
    if isinstance(err, NotASession):
        return _fail(f"{err.path} is not a session directory.", Exit.UNREADABLE)
    return _fail(f"Could not recover: {err.hint or type(err).__name__}", Exit.UNREADABLE)


def cmd_recover(session_dir: Path, *, recover_stale: bool = False) -> Result[int, CliFailure]:
    """Open a NEW version continuing from a session's verified part; never overwrites.

    `recover_stale` is the explicit user action that takes over a dead process's data-root lock.
    """
    resumed = resume_session(session_dir, recover_stale=recover_stale)
    if resumed.is_err:
        failure = _recover_failure(resumed.danger_err)
        _log.warning("recover %s refused: %s", session_dir, failure.message)
        return Err(failure)
    handle = resumed.danger_ok
    closed = handle.close()
    if closed.is_err:
        _log.error("closing recovered session %s failed: %s", handle.path, closed.danger_err)
        return Err(_fail("Created the new version but could not finalise it.", Exit.UNREADABLE))
    _out(f"Created new version {handle.path.name} continuing from {session_dir.name}.")
    _out(f"{session_dir.name} was not modified.")
    return Ok(Exit.OK)


def _payload_text(flags: int, payload: bytes) -> str:
    """Render a record payload: JSON/text as UTF-8, binary as hex."""
    if flags & FLAG_JSON:
        return payload.decode("utf-8", errors="replace")
    return payload.hex()


def _type_name(code: int) -> str:
    """Return the registered record type name, or `0xNN` for unregistered codes."""
    try:
        return RecordType(code).name
    except ValueError:
        return f"0x{code:02x}"


@propagate
def cmd_export(session_dir: Path, target: Path, *, excel_bom: bool) -> Result[int, CliFailure]:
    """Write the verified records of a session to a NEW csv; refuses an existing target."""
    opened = _open(session_dir)
    ro = opened.unwrap()
    if ro.scan is None:
        if ro.scan_error is not None:
            return Err(_fail("Refused: the recording is damaged; run `verify`.", Exit.CORRUPT))
        return Err(_fail("This session has no WAL to export.", Exit.UNREADABLE))
    rows: list[list[str | int]] = []
    for item in WalReader(session_dir / "wal").records():
        rec = item.unwrap(
            err=_fail("Refused: the recording is damaged; run `verify`.", Exit.CORRUPT)
        )
        rows.append(
            [rec.seq, rec.wall_ns, _type_name(rec.type), _payload_text(rec.flags, rec.payload)]
        )
    written = write_csv_exclusive(target, _EXPORT_HEADER, rows, excel_bom=excel_bom)
    if written.is_err:
        _log.warning("export to %s refused: %s", target, written.danger_err)
        return Err(_fail(f"Refused: {target} already exists or cannot be created.", Exit.REFUSED))
    _out(f"Wrote {len(rows)} records to {target} ({written.danger_ok} bytes).")
    if ro.scan.tail is not None:
        _out("note: unverified bytes at the end of the log were not exported.")
    return Ok(Exit.OK)


def build_parser() -> argparse.ArgumentParser:
    """Build the `sadi store` argument parser."""
    parser = argparse.ArgumentParser(prog="sadi store", description="Inspect and recover sessions.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_list = sub.add_parser("list", help="list sessions under a data root (read-only)")
    p_list.add_argument("root", type=Path)
    p_verify = sub.add_parser("verify", help="check every WAL checksum of a session (read-only)")
    p_verify.add_argument("session", type=Path)
    p_rec = sub.add_parser("recover", help="open a NEW version from a session's verified part")
    p_rec.add_argument("session", type=Path)
    p_rec.add_argument(
        "--recover-stale",
        action="store_true",
        help="take over a data-root lock left by a process that exited uncleanly",
    )
    p_exp = sub.add_parser("export", help="write a session's verified records to a NEW csv")
    p_exp.add_argument("session", type=Path)
    p_exp.add_argument("target", type=Path)
    p_exp.add_argument("--excel-bom", action="store_true", help="prefix a UTF-8 BOM for Excel")
    return parser


def run(args: argparse.Namespace) -> Result[int, CliFailure]:
    """Dispatch parsed arguments to the subcommand."""
    if args.command == "list":
        return cmd_list(args.root)
    if args.command == "verify":
        return cmd_verify(args.session)
    if args.command == "recover":
        return cmd_recover(args.session, recover_stale=args.recover_stale)
    return cmd_export(args.session, args.target, excel_bom=args.excel_bom)


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point; returns the process exit code."""
    args = build_parser().parse_args(argv)
    result = run(args)
    if result.is_err:
        failure = result.danger_err
        _err(failure.message)
        return failure.code
    return result.danger_ok


if __name__ == "__main__":
    sys.exit(main())
