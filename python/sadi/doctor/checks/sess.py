"""SESS checks: session directory layout, locks, leftovers, family chain, permissions."""

# frob:ticket 01M6WJHRTR9DZMZGR04GT1SN0C
from __future__ import annotations

from collections.abc import Callable

from sadi.doctor.checks.data import _NETWORK_FS, _root
from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity, Step
from sadi.doctor.sessions import SessionFacts
from sadi.doctor.steps import action, cmd, manual

_DEP = ("DATA-010",)


def survey(ctx: Ctx, deep: bool = False) -> list[SessionFacts]:
    """Return the read-only session survey for the resolved data root."""
    return ctx.probes.session_facts(_root(ctx), deep)


def hits(found: list[SessionFacts], pred: Callable[[SessionFacts], bool]) -> list[SessionFacts]:
    """Return the sessions matching a predicate."""
    return [s for s in found if pred(s)]


def listing(os: Os, path: str) -> str:
    """Return a read-only directory listing command for the OS."""
    return f"Get-ChildItem -Force '{path}'" if os is Os.WINDOWS else f"ls -la '{path}'"


def first_path(out: Outcome, ctx: Ctx) -> str:
    """Return the first affected session path recorded in the outcome, else the sessions dir."""
    paths = out.facts.get("paths")
    if isinstance(paths, list) and paths:
        return paths[0]
    return f"{_root(ctx)}/sessions"


def names(rows: list[SessionFacts]) -> dict[str, list[str]]:
    """Facts naming the affected sessions and their paths."""
    return {"sessions": [s.name for s in rows], "paths": [s.path for s in rows]}


def _look(ctx: Ctx, out: Outcome) -> Step:
    """Build the shared read-only 'look at it' step."""
    path = first_path(out, ctx)
    return action(
        "List the affected session folder (read-only).",
        "You see the files described in the finding.",
        cmd(ctx.os, listing(ctx.os, path)),
    )


def _flag(rows: list[SessionFacts], mode: str, text: str) -> Outcome | None:
    """Build a warn outcome for the matching sessions, or None when there are none."""
    if not rows:
        return None
    facts = names(rows)
    head = f"{text}: {', '.join(s.name for s in rows[:3])}" + (" ..." if len(rows) > 3 else "")
    return warn(mode, head, **facts)


@check(
    "SESS-010",
    Layer.SESS,
    "Session directory names and layout",
    Severity.WARNING,
    {
        "foreign-dir": "A directory not created by SADI sits in the sessions folder",
        "incomplete": "A session folder has no valid first WAL segment",
        "manifest-unparseable": "manifest.json cannot be read",
        "manifest-stale": "manifest.json is missing or out of date (derived cache)",
    },
    "Name pattern, wal/ children and manifest parse via the store, read-only",
    depends_on=_DEP,
)
def sess_010(ctx: Ctx) -> Outcome:
    """Classify the worst layout problem across session directories."""
    found = survey(ctx)
    probes: tuple[tuple[str, str, Callable[[SessionFacts], bool]], ...] = (
        ("foreign-dir", "Not a SADI session folder", lambda s: not s.name_ok),
        ("incomplete", "No valid first WAL segment", lambda s: s.name_ok and s.incomplete),
        (
            "manifest-unparseable",
            "Unreadable manifest",
            lambda s: s.manifest == "unparseable",
        ),
        (
            "manifest-stale",
            "Manifest missing or stale",
            lambda s: s.name_ok and not s.incomplete and s.manifest_stale,
        ),
    )
    for mode, text, pred in probes:
        res = _flag(hits(found, pred), mode, text)
        if res is not None:
            return res
    return ok(f"{len(found)} session folder(s) look well formed", count=len(found))


@remedy("SESS-010", "foreign-dir")
def _sess_010_foreign(ctx: Ctx, out: Outcome) -> Fix:
    """Explain that foreign folders are never touched."""
    return Fix(
        "Leave the folder alone or move it yourself",
        (
            _look(ctx, out),
            manual(
                "If you did not put this folder there, move it out of the sessions folder yourself.",
                "SADI no longer lists it; the doctor never moves or deletes it.",
                mutates=Mutates.DATA,
                changes="Moves a folder that is not a SADI recording.",
                if_not="Leaving it is harmless; SADI ignores folders it did not create.",
            ),
        ),
    )


@remedy("SESS-010", "incomplete")
def _sess_010_incomplete(ctx: Ctx, out: Outcome) -> Fix:
    """Incomplete sessions are skipped by the app."""
    return Fix(
        "Ignore the incomplete session folder",
        (
            _look(ctx, out),
            manual(
                "Nothing to do: SADI skips a folder whose first WAL segment was never written.",
                "The folder does not appear in the session list.",
                if_not="If you expected data here, keep the folder and ask for help; do not delete it.",
            ),
        ),
    )


@remedy("SESS-010", "manifest-unparseable")
def _sess_010_unparseable(ctx: Ctx, out: Outcome) -> Fix:
    """The manifest is a derived cache, rebuilt on the next writable open."""
    return Fix(
        "Let SADI rebuild the manifest",
        (
            _look(ctx, out),
            manual(
                "Open the session from the SADI session list and resume it; manifest.json is rebuilt from the WAL.",
                "The session opens and its recorded data is intact.",
                mutates=Mutates.DATA,
                changes="SADI rewrites manifest.json (a derived cache); the WAL is not changed.",
                if_not="If it will not open, copy the whole folder somewhere safe and ask for help.",
            ),
        ),
    )


@remedy("SESS-010", "manifest-stale")
def _sess_010_stale(ctx: Ctx, out: Outcome) -> Fix:
    """A stale manifest is harmless and refreshed on open."""
    return Fix(
        "Nothing to fix: the manifest refreshes itself",
        (
            _look(ctx, out),
            manual(
                "Open the session in SADI once; the manifest is refreshed from the WAL.",
                "The stale-manifest note disappears on the next doctor run.",
                mutates=Mutates.DATA,
                changes="SADI rewrites manifest.json (a derived cache).",
            ),
        ),
    )


def _alive(s: SessionFacts) -> bool:
    """True when the lock holder is a running writer."""
    return bool(s.lock_holder) and s.holder_alive is True


def _crashed(s: SessionFacts) -> bool:
    """True when a dead holder left an open (never closed) session."""
    return s.state in ("open", "crashed") and bool(s.lock_holder) and s.holder_alive is False


@check(
    "SESS-020",
    Layer.SESS,
    "Locks: live holders and crashed sessions",
    Severity.WARNING,
    {
        "locked-live": "SADI is open on this session right now",
        "locked-dead-pid-reused": "The lock names a pid that now belongs to another process",
        "crashed": "The session was not closed and its writer is gone",
        "lock-on-network-fs": "Session locks live on a network filesystem",
    },
    "read_lock_holder plus the liveness token; the lock is never acquired",
    depends_on=_DEP,
)
def sess_020(ctx: Ctx) -> Outcome:
    """Report lock holders and unclosed sessions without touching the lock."""
    found = survey(ctx)
    fs = ctx.probes.fstype(_root(ctx))
    if fs in _NETWORK_FS and any(s.lock_holder for s in found):
        return warn("lock-on-network-fs", f"Session locks are on {fs}", fs=fs or "")
    probes: tuple[tuple[str, str, Callable[[SessionFacts], bool]], ...] = (
        ("crashed", "Not closed and the writer is gone", _crashed),
        ("locked-dead-pid-reused", "Lock pid reused by another process", lambda s: s.pid_reused),
        ("locked-live", "In use by a running SADI", _alive),
    )
    for mode, text, pred in probes:
        res = _flag(hits(found, pred), mode, text)
        if res is not None:
            return res
    return ok("No live or abandoned session locks", count=len(found))


@remedy("SESS-020", "locked-live")
def _sess_020_live(ctx: Ctx, out: Outcome) -> Fix:
    """Point at the running SADI."""
    return Fix(
        "Use the SADI that already has the session open",
        (
            manual(
                "Switch to the running SADI window, or close it, before opening the session elsewhere.",
                "Only one SADI has the session open.",
                if_not="If no SADI is running, see the crashed or pid-reused findings.",
            ),
        ),
    )


@remedy("SESS-020", "locked-dead-pid-reused")
def _sess_020_reused(ctx: Ctx, out: Outcome) -> Fix:
    """The lock is stale; the app recovers it."""
    return Fix(
        "Resume from the app; the stale lock is recognised",
        (
            _look(ctx, out),
            manual(
                "Resume the session from SADI; it checks the process start time and takes over the lock.",
                "The session opens for writing.",
                mutates=Mutates.DATA,
                changes="SADI rewrites the lock line for the session.",
            ),
        ),
    )


@remedy("SESS-020", "crashed")
def _sess_020_crashed(ctx: Ctx, out: Outcome) -> Fix:
    """Resume from the app to continue."""
    return Fix(
        "Resume the unclosed session from the app",
        (
            _look(ctx, out),
            manual(
                "Open SADI and resume the session from the session list.",
                "SADI verifies the recording, keeps everything shown as saved and continues it.",
                mutates=Mutates.DATA,
                changes="SADI appends to the recording and rewrites the manifest.",
                if_not="Do not delete the folder; copy it somewhere safe and ask for help.",
            ),
        ),
    )


@remedy("SESS-020", "lock-on-network-fs")
def _sess_020_netfs(ctx: Ctx, out: Outcome) -> Fix:
    """File locks on network filesystems are unreliable."""
    return Fix(
        "Move the data folder to a local disk",
        (
            manual(
                "Choose a data folder on a local disk (SADI_DATA_ROOT) and copy finished sessions over by hand.",
                "The doctor reports a local filesystem for the data folder.",
                mutates=Mutates.DATA_DIR,
                changes="Changes where new sessions are stored.",
                if_not="Never run two SADI instances against the same network folder.",
            ),
        ),
    )


@check(
    "SESS-030",
    Layer.SESS,
    "Orphans and leftovers",
    Severity.INFO,
    {
        "tmp-leftovers": "Temporary files from an interrupted write remain",
        "export-without-sidecar": "An export has no .prov.json sidecar",
    },
    ".tmp files and exports without a sidecar, listed only",
    depends_on=_DEP,
)
def sess_030(ctx: Ctx) -> Outcome:
    """Count leftovers; nothing is ever deleted."""
    found = survey(ctx)
    orphans = hits(found, lambda s: bool(s.orphan_exports))
    res = _flag(orphans, "export-without-sidecar", "Export without provenance sidecar")
    if res is not None:
        return res
    res = _flag(hits(found, lambda s: bool(s.tmp_files)), "tmp-leftovers", "Temporary leftovers")
    return res or ok("No leftovers", count=len(found))


@remedy("SESS-030", "tmp-leftovers")
def _sess_030_tmp(ctx: Ctx, out: Outcome) -> Fix:
    """Leftover tmp files are harmless."""
    return Fix(
        "Leave the temporary files; they are harmless",
        (
            _look(ctx, out),
            manual(
                "Nothing to do. SADI ignores these files and the doctor never deletes them.",
                "The files remain and nothing else is affected.",
                mutates=Mutates.DATA,
                changes="Optional: you may delete leftover .tmp files yourself once SADI is closed.",
            ),
        ),
    )


@remedy("SESS-030", "export-without-sidecar")
def _sess_030_sidecar(ctx: Ctx, out: Outcome) -> Fix:
    """Re-export to get a complete export."""
    return Fix(
        "Export again to get a complete file with its sidecar",
        (
            _look(ctx, out),
            manual(
                "Open the session in SADI and export it again.",
                "The new export has a .prov.json sidecar next to it.",
                mutates=Mutates.DATA,
                changes="Writes a new export file; the old one is left in place.",
            ),
        ),
    )


def _chain(
    found: list[SessionFacts],
) -> tuple[list[SessionFacts], list[SessionFacts], list[SessionFacts]]:
    """Return (version gaps, parent mismatches, missing parents) over session families."""
    by_name = {s.name: s for s in found}
    fams: dict[str, list[int]] = {}
    for s in found:
        if s.name_ok:
            fams.setdefault(s.family, []).append(s.version)
    gaps = [
        s
        for s in found
        if s.name_ok and s.version > 1 and (s.version - 1) not in fams.get(s.family, [])
    ]
    missing: list[SessionFacts] = []
    mismatch: list[SessionFacts] = []
    for s in found:
        if s.parent is None:
            continue
        par = by_name.get(s.parent)
        if par is None:
            missing.append(s)
        elif (
            par.last_seq is not None
            and s.parent_last_seq is not None
            and par.last_seq < s.parent_last_seq
        ) or par.family != s.family:
            mismatch.append(s)
    return (gaps, mismatch, missing)


@check(
    "SESS-040",
    Layer.SESS,
    "Family chain consistency",
    Severity.ERROR,
    {
        "version-gap": "A session family skips a version number",
        "parent-mismatch": "A session disagrees with its parent about where it forked",
        "parent-missing": "A session's parent folder is absent",
    },
    "Versions contiguous; parent and parent_last_seq match the parent's scan",
    depends_on=_DEP,
)
def sess_040(ctx: Ctx) -> Outcome:
    """Check each family's version chain without modifying anything."""
    gaps, mismatch, missing = _chain(survey(ctx))
    for mode, rows, text in (
        ("parent-mismatch", mismatch, "Parent mismatch"),
        ("parent-missing", missing, "Parent folder missing"),
        ("version-gap", gaps, "Version gap"),
    ):
        if rows:
            head = f"{text}: {', '.join(s.name for s in rows[:3])}"
            maker = warn if mode == "parent-missing" else fail
            return maker(mode, head, **names(rows))
    return ok("Session families are consistent")


@remedy("SESS-040", "version-gap")
def _sess_040_gap(ctx: Ctx, out: Outcome) -> Fix:
    """A gap usually means a folder was moved or deleted by hand."""
    return Fix(
        "Find the missing version before relying on the chain",
        (
            _look(ctx, out),
            manual(
                "Look for the missing version in backups or another disk and put it back by hand.",
                "The version numbers are contiguous again.",
                mutates=Mutates.DATA,
                changes="Restores a session folder you moved or deleted earlier.",
                if_not="Each session still opens on its own; the gap only affects family history.",
            ),
        ),
    )


@remedy("SESS-040", "parent-mismatch")
def _sess_040_mismatch(ctx: Ctx, out: Outcome) -> Fix:
    """Never auto-fixed: tampering or a copy error."""
    return Fix(
        "Keep both folders and review them before continuing",
        (
            _look(ctx, out),
            manual(
                "Do not resume either session. Copy both folders to safe storage and compare them.",
                "You know which copy is the original.",
                if_not="Ask for help; the doctor will not change either folder.",
            ),
        ),
    )


@remedy("SESS-040", "parent-missing")
def _sess_040_missing(ctx: Ctx, out: Outcome) -> Fix:
    """The family was partially moved."""
    return Fix(
        "Put the parent folder back next to this session",
        (
            _look(ctx, out),
            manual(
                "Move the parent session folder back into the sessions folder (copy it, do not delete anything).",
                "The parent folder is listed beside the session.",
                mutates=Mutates.DATA,
                changes="Restores the parent folder.",
                if_not="The child session still opens on its own.",
            ),
        ),
    )


@check(
    "SESS-050",
    Layer.SESS,
    "Permissions and ownership",
    Severity.WARNING,
    {
        "not-owned-by-user": "A session folder belongs to another user",
        "read-only-session": "A session folder cannot be written (cannot be resumed)",
    },
    "os.stat owner and os.access on each session directory",
    depends_on=_DEP,
)
def sess_050(ctx: Ctx) -> Outcome:
    """Report ownership and write access problems."""
    found = survey(ctx)
    res = _flag(hits(found, lambda s: s.not_owned), "not-owned-by-user", "Owned by another user")
    if res is not None:
        return res
    res = _flag(hits(found, lambda s: s.read_only), "read-only-session", "Not writable")
    return res or ok("Session folders are yours and writable", count=len(found))


@remedy("SESS-050", "not-owned-by-user")
def _sess_050_owner(ctx: Ctx, out: Outcome) -> Fix:
    """Show owners; changing them needs an administrator."""
    path = first_path(out, ctx)
    show = f"icacls '{path}'" if ctx.os is Os.WINDOWS else f"ls -ld '{path}'"
    return Fix(
        "Take over the folder or open it as its owner",
        (
            action(
                "Show the owner and permissions.", "You see who owns the folder.", cmd(ctx.os, show)
            ),
            manual(
                "Ask the owner or an administrator to give your account ownership, or copy the folder to your own data folder.",
                "You own the folder and can write to it.",
                mutates=Mutates.DATA,
                changes="Changes the owner or permissions of the session folder.",
            ),
        ),
    )


@remedy("SESS-050", "read-only-session")
def _sess_050_ro(ctx: Ctx, out: Outcome) -> Fix:
    """Read-only sessions can be reviewed but not resumed."""
    path = first_path(out, ctx)
    show = f"icacls '{path}'" if ctx.os is Os.WINDOWS else f"ls -ld '{path}'"
    return Fix(
        "Make the folder writable if you want to resume it",
        (
            action(
                "Show the permissions.",
                "The folder lacks write permission for you.",
                cmd(ctx.os, show),
            ),
            manual(
                "Grant your account write access (on Linux or macOS: chmod u+w on the folder), or just review it read-only.",
                "The doctor no longer reports the folder as read-only.",
                mutates=Mutates.DATA,
                changes="Adds write permission to the session folder.",
                if_not="Reviewing and exporting still work without write access.",
            ),
        ),
    )
