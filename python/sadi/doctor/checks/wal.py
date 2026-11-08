"""WAL checks: integrity scans of recorded sessions, snapshots and settings, all read-only."""

# frob:ticket 01M6WJHRTR9DZMZGR04GT1SN0C
from __future__ import annotations

from collections.abc import Callable

from sadi.doctor.checks.sess import first_path, hits, listing, names, survey
from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Mutates, Severity, SkipReason, Step
from sadi.doctor.sessions import SessionFacts
from sadi.doctor.steps import action, cmd, manual

_DEPS = ("DATA-010", "SESS-010")
_QUICK = {
    "torn-tail": "The last write was cut short (normal after a crash)",
    "corrupt": "A record is damaged in the middle of the recording",
    "unsupported-format": "A newer SADI wrote this recording",
    "header-invalid": "A segment header is damaged or missing",
}
_DEEP_EXTRA = {
    "seal-mismatch": "A sealed segment no longer matches its recorded hash",
    "seq-gap": "Record numbers skip or repeat",
    "deep-timeout": "The full scan ran out of time before covering every session",
}
_FAIL_MODES = frozenset({"corrupt", "seal-mismatch", "seq-gap"})
_ORDER = (
    "corrupt",
    "seal-mismatch",
    "seq-gap",
    "header-invalid",
    "unsupported-format",
    "torn-tail",
    "deep-timeout",
)


def _scan_outcome(found: list[SessionFacts], allowed: frozenset[str], deep: bool) -> Outcome:
    """Pick the worst WAL status among sessions and build the outcome."""

    def mode_of(s: SessionFacts) -> str:
        w = s.wal
        if w == "timeout":
            return "deep-timeout"
        if w in ("seal-mismatch", "seq-gap") and w not in allowed:
            return "corrupt"
        return w

    for mode in _ORDER:
        if mode not in allowed:
            continue
        rows = hits(found, lambda s, m=mode: mode_of(s) == m)  # type: ignore[misc]
        if not rows:
            continue
        detail = "; ".join(f"{s.name}: {s.wal_detail}" for s in rows[:2] if s.wal_detail)
        head = f"{mode}: {', '.join(s.name for s in rows[:3])}" + (f" ({detail})" if detail else "")
        facts = {**names(rows), "tail_bytes": rows[0].tail_bytes}
        maker = fail if mode in _FAIL_MODES else warn
        return maker(mode, head, **facts)
    scanned = sum(1 for s in found if s.wal in ("ok",))
    return ok(f"{scanned} recording(s) verified", count=len(found), deep=deep)


@check(
    "WAL-010",
    Layer.WAL,
    "Quick scan: headers, last segment tail",
    Severity.WARNING,
    _QUICK,
    "WalReader.scan over sessions under 256 MiB (read-only); larger ones need --deep",
    depends_on=_DEPS,
)
def wal_010(ctx: Ctx) -> Outcome:
    """Scan small recordings for torn tails, corruption and header problems."""
    return _scan_outcome(survey(ctx), frozenset(_QUICK), deep=False)


@check(
    "WAL-020",
    Layer.WAL,
    "Full scan: every record CRC and every seal hash",
    Severity.WARNING,
    {**_QUICK, **_DEEP_EXTRA},
    "WalReader.scan of every session, bounded by a time budget (read-only)",
    depends_on=_DEPS,
    opt_in_flag="deep",
)
def wal_020(ctx: Ctx) -> Outcome:
    """Fully verify every recording, whatever its size."""
    if not ctx.options.deep:
        return skip(SkipReason.OPT_IN, "Needs --deep")
    return _scan_outcome(survey(ctx, deep=True), frozenset(_QUICK) | frozenset(_DEEP_EXTRA), True)


def _look(ctx: Ctx, out: Outcome) -> Step:
    """Build the shared read-only listing step."""
    return action(
        "List the recording's files (read-only).",
        "You see wal/ with its seg-*.wal files.",
        cmd(ctx.os, listing(ctx.os, first_path(out, ctx) + "/wal")),
    )


def _both(mode: str) -> Callable[[Callable[[Ctx, Outcome], Fix]], Callable[[Ctx, Outcome], Fix]]:
    """Register one remedy function for a mode of both WAL-010 and WAL-020."""

    def deco(fn: Callable[[Ctx, Outcome], Fix]) -> Callable[[Ctx, Outcome], Fix]:
        remedy("WAL-010", mode)(fn)
        remedy("WAL-020", mode)(fn)
        return fn

    return deco


@_both("torn-tail")
def _torn_tail(ctx: Ctx, out: Outcome) -> Fix:
    """A torn tail is normal after a crash; resuming is safe."""
    return Fix(
        "Resume from the app; nothing shown as saved is lost",
        (
            _look(ctx, out),
            manual(
                "Open SADI and resume the session. The incomplete last write is set aside, with its bytes kept, before new data is added.",
                "The session resumes and the doctor no longer reports a torn tail.",
                mutates=Mutates.DATA,
                changes="SADI moves the unfinished tail aside (kept) and appends new records.",
                if_not="Do not truncate the file yourself; copy the folder somewhere safe first.",
            ),
        ),
    )


@_both("corrupt")
def _corrupt(ctx: Ctx, out: Outcome) -> Fix:
    """Damaged recordings are kept for review and never resumed."""
    return Fix(
        "Do not resume; keep the folder and start a new session",
        (
            _look(ctx, out),
            manual(
                "Copy the whole session folder to safe storage. Do not resume it.",
                "You have an untouched copy.",
            ),
            manual(
                "Start a new session in SADI. Open the damaged one for review only; the verified part can still be viewed and exported.",
                "The new session records normally.",
                if_not="Ask for help and attach the doctor report; do not delete the damaged folder.",
            ),
        ),
    )


@_both("unsupported-format")
def _unsupported(ctx: Ctx, out: Outcome) -> Fix:
    """Newer SADI wrote the recording; upgrade to read it."""
    return Fix(
        "Open it with a newer SADI",
        (
            manual(
                "Update SADI to the latest version, then open the session again.",
                "The doctor no longer reports an unsupported format.",
                if_not="Do not edit the files; keep the folder as it is.",
            ),
        ),
    )


@_both("header-invalid")
def _header(ctx: Ctx, out: Outcome) -> Fix:
    """Header damage is treated like corruption."""
    return Fix(
        "Keep the folder; do not resume it",
        (
            _look(ctx, out),
            manual(
                "Copy the session folder to safe storage and ask for help; the doctor will not repair headers.",
                "You have an untouched copy.",
                if_not="Never delete or rename wal files.",
            ),
        ),
    )


@remedy("WAL-020", "seal-mismatch")
def _seal(ctx: Ctx, out: Outcome) -> Fix:
    """A sealed segment changed after sealing."""
    return Fix(
        "Treat the recording as damaged; keep it and start a new session",
        (
            _look(ctx, out),
            manual(
                "Copy the folder to safe storage and start a new session. The segment was modified after it was sealed (disk error or tampering).",
                "You have an untouched copy and a fresh session.",
                if_not="Do not resume or edit the damaged session.",
            ),
        ),
    )


@remedy("WAL-020", "seq-gap")
def _gap(ctx: Ctx, out: Outcome) -> Fix:
    """A segment or record is missing."""
    return Fix(
        "Look for the missing segment file before anything else",
        (
            _look(ctx, out),
            manual(
                "Check backups or other disks for the missing seg-*.wal file and put it back by hand; otherwise keep the folder as is.",
                "The segment numbers are contiguous and the next doctor run is clean.",
                mutates=Mutates.DATA,
                changes="Restores a segment file you moved or deleted.",
                if_not="Do not resume this session; the verified part is still viewable.",
            ),
        ),
    )


@remedy("WAL-020", "deep-timeout")
def _timeout(ctx: Ctx, out: Outcome) -> Fix:
    """Run the full scan again with a larger budget."""
    return Fix(
        "Run the full scan again when the machine is idle",
        (
            action(
                "Run the full scan for the remaining sessions.",
                "The scan finishes without a timeout.",
                cmd(ctx.os, "sadi-doctor run --deep --only WAL-020"),
                if_not="Verify very large sessions one at a time by closing other programs first.",
            ),
        ),
    )


@check(
    "WAL-030",
    Layer.WAL,
    "Snapshot validity",
    Severity.INFO,
    {
        "stale-snapshots": "Snapshots cover more than the recording holds (ignored by replay)",
        "invalid-snapshot": "A snapshot file is damaged (ignored by replay)",
    },
    "snapshots/snap-*.snap parse and prefix hashes match the WAL (read-only)",
    depends_on=_DEPS,
)
def wal_030(ctx: Ctx) -> Outcome:
    """List snapshots replay will ignore; none are deleted."""
    found = survey(ctx)
    for mode, rows, text in (
        ("invalid-snapshot", hits(found, lambda s: s.snapshots_invalid > 0), "Invalid snapshot"),
        ("stale-snapshots", hits(found, lambda s: s.snapshots_stale > 0), "Stale snapshot"),
    ):
        if rows:
            return warn(mode, f"{text}: {', '.join(s.name for s in rows[:3])}", **names(rows))
    return ok("Snapshots are valid", count=len(found))


@remedy("WAL-030", "stale-snapshots")
def _stale(ctx: Ctx, out: Outcome) -> Fix:
    """Stale snapshots are ignored and rebuilt."""
    return Fix(
        "Nothing to fix: replay ignores stale snapshots",
        (
            manual(
                "No action needed; SADI replays the WAL and writes a fresh snapshot later.",
                "The session opens normally.",
                if_not="You may leave the files in snapshots/; they are never deleted automatically.",
            ),
        ),
    )


@remedy("WAL-030", "invalid-snapshot")
def _invalid(ctx: Ctx, out: Outcome) -> Fix:
    """Invalid snapshots are ignored and never deleted."""
    return Fix(
        "Nothing to fix: replay ignores damaged snapshots",
        (
            manual(
                "No action needed; the WAL is the source of truth and the snapshot is only a speed-up.",
                "The session opens normally, a little slower.",
                if_not="Keep the file if you want to report it.",
            ),
        ),
    )


@check(
    "WAL-040",
    Layer.WAL,
    "Settings record precedes raw data",
    Severity.ERROR,
    {"undecodable-version": "Raw data appears before any SETTINGS record"},
    "WalReader.records(): first RAW_BLOCK must follow a SETTINGS record (read-only)",
    depends_on=_DEPS,
)
def wal_040(ctx: Ctx) -> Outcome:
    """Find recordings whose raw data cannot be scaled."""
    rows = hits(survey(ctx), lambda s: s.raw_before_settings)
    if rows:
        return fail(
            "undecodable-version",
            f"Raw data without settings: {', '.join(s.name for s in rows[:3])}",
            **names(rows),
        )
    return ok("Every recording declares its settings first")


@remedy("WAL-040", "undecodable-version")
def _undecodable(ctx: Ctx, out: Outcome) -> Fix:
    """Raw data cannot be scaled without settings."""
    return Fix(
        "Export the raw data and contact support",
        (
            _look(ctx, out),
            manual(
                "Open the session read-only in SADI and export the raw data; send the exported file with the doctor report.",
                "You have the raw export saved.",
                if_not="Do not resume this session; keep the folder untouched.",
            ),
        ),
    )
