"""DATA checks: data root location, filesystem, space, spill files."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import tomllib

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity, SkipReason
from sadi.doctor.steps import action, cmd, manual

GIB = 1024**3
MIN_FREE_BYTES = 2 * GIB
LOW_FREE_BYTES = 10 * GIB
_NETWORK_FS = {
    "nfs",
    "nfs4",
    "cifs",
    "smb3",
    "smbfs",
    "sshfs",
    "fuse.sshfs",
    "fuse.rclone",
    "afs",
    "afpfs",
    "webdav",
}  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
_FAT_FS = {"vfat", "exfat", "msdos", "fat32"}
_DRVFS = {"9p", "drvfs"}
SLOW_FSYNC_MS = 200.0
LOG_LIMIT_BYTES = GIB
LOG_DIR = "logs"
CONFIG_FILE = "config.toml"
SHARING_MARK = "DurableSharingViolation"
EXCLUSIONS_PS = ("powershell", "-NoProfile", "-Command", "(Get-MpPreference).ExclusionPath")


def _root(ctx: Ctx) -> str:
    """Return the resolved data root (the runner always provides one)."""
    return ctx.data_root or ctx.probes.user_data_dir()


@check(
    "DATA-010",
    Layer.DATA,
    "Data root resolved and usable",
    Severity.BLOCKER,
    {
        "missing": "The data root does not exist yet (first run)",
        "not-a-directory": "The data root path is a file",
        "not-writable": "The current user cannot write the data root",
    },
    "Path.exists, is_dir, os.access(W_OK); nothing is created",
)
def data_010(ctx: Ctx) -> Outcome:
    """Read-only look at the data root."""
    root = _root(ctx)
    if not ctx.probes.exists(root):
        return fail("missing", f"Data root {root} does not exist", root=root)
    if not ctx.probes.is_dir(root):
        return fail("not-a-directory", f"{root} is not a directory", root=root)
    if not ctx.probes.writable(root):
        return fail("not-writable", f"{root} is not writable by you", root=root)
    return ok(f"Data root {root} is usable", root=root)


@remedy("DATA-010", "missing")
def _data_010_missing(ctx: Ctx, out: Outcome) -> Fix:
    """Create the missing data root (owner-only), or let SADI create it on first start."""
    root = _root(ctx)
    if ctx.os is Os.WINDOWS:
        mk = f"New-Item -ItemType Directory -Path '{root}'"
    else:
        mk = f"mkdir -p -m 700 '{root}'"
    return Fix(
        "Create the data root",
        (
            action(
                f"Create the data folder {root} (the configured --data-root or SADI_DATA_ROOT, "
                "else the default). Skip this step to let SADI create it on the Setup screen.",
                "The command prints nothing (or the new folder) and no error.",
                cmd(ctx.os, mk),
                mutates=Mutates.DATA_DIR,
                changes=f"Creates the empty folder {root}; an existing folder is left untouched.",
                if_not="Choose a local, writable disk with --data-root or SADI_DATA_ROOT.",
            ),
        ),
    )


@remedy("DATA-010", "not-a-directory")
def _data_010_file(ctx: Ctx, out: Outcome) -> Fix:
    """Move a file out of the way."""
    root = _root(ctx)
    show = f"Get-Item '{root}' | Format-List" if ctx.os is Os.WINDOWS else f"ls -ld '{root}'"
    return Fix(
        "Choose a different data folder",
        (
            action(
                "Look at what is at that path.",
                "It is listed as a file, not a folder.",
                cmd(ctx.os, show),
            ),
            manual(
                "Point SADI at another folder with SADI_DATA_ROOT (do not delete the file unless you know what it is).",
                "The doctor reports the new folder.",
            ),
        ),
    )


@remedy("DATA-010", "not-writable")
def _data_010_perm(ctx: Ctx, out: Outcome) -> Fix:
    """Show ownership and suggest a writable root."""
    root = _root(ctx)
    show = f"icacls '{root}'" if ctx.os is Os.WINDOWS else f"ls -ld '{root}'"
    return Fix(
        "Make the data folder writable",
        (
            action(
                "Show who owns the folder.",
                "Your user is the owner or has write rights.",
                cmd(ctx.os, show),
            ),
            manual(
                "Fix the ownership or choose another folder with SADI_DATA_ROOT.",
                "The first command now shows write access for you.",
                mutates=Mutates.SYSTEM,
                changes="Changes folder permissions or the configured data folder.",
            ),
        ),
    )


@check(
    "DATA-020",
    Layer.DATA,
    "Filesystem is safe for durability",
    Severity.BLOCKER,
    {
        "network-fs": "The data root is on a network filesystem",
        "drvfs-9p": "The data root is on a Windows drive seen from WSL",
        "fat-exfat": "The data root is on FAT/exFAT (no reliable flush)",
    },
    "filesystem type of the longest matching mount: /proc/mounts (Linux/WSL), `mount` (macOS), GetVolumeInformationW (Windows)",
)
def data_020(ctx: Ctx) -> Outcome:
    """Reject filesystems where fsync or locks are unreliable."""
    root = _root(ctx)
    fs = ctx.probes.fstype(root)  # frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
    if fs is None:
        return skip(SkipReason.TOOL_MISSING, "Could not determine the filesystem type", root=root)
    if fs in _NETWORK_FS and not ctx.options.allow_network_fs:
        return fail("network-fs", f"{root} is on {fs}", fs=fs, root=root)
    if fs in _DRVFS and ctx.os is Os.WSL:
        return fail("drvfs-9p", f"{root} is on a Windows drive ({fs})", fs=fs, root=root)
    if fs in _FAT_FS:
        return warn("fat-exfat", f"{root} is on {fs}", fs=fs, root=root)
    return ok(f"{root} is on {fs}", fs=fs, root=root)


@remedy("DATA-020", "network-fs")
def _data_020_net(ctx: Ctx, out: Outcome) -> Fix:
    """Move the root to a local disk."""
    root = _root(ctx)
    return Fix(
        "Use a local disk",
        (
            action(
                "Confirm the filesystem type.",
                "The Type column shows a network type.",
                cmd(ctx.os, f"df -T '{root}'"),
            ),
            manual(
                "Choose a folder on an internal disk and set SADI_DATA_ROOT to it.",
                "The doctor reports a local filesystem.",
                mutates=Mutates.DATA_DIR,
                changes="Changes which folder holds new sessions; existing sessions are not moved.",
            ),
        ),
    )


@remedy("DATA-020", "drvfs-9p")
def _data_020_drvfs(ctx: Ctx, out: Outcome) -> Fix:
    """Move the root into the WSL filesystem."""
    return Fix(
        "Keep the data inside the WSL filesystem",
        (
            manual(
                "Set SADI_DATA_ROOT to a folder under your Linux home, for example ~/sadi-data, not /mnt/c/....",
                "The doctor reports ext4.",
                mutates=Mutates.DATA_DIR,
                changes="Changes which folder holds new sessions; existing sessions are not moved.",
            ),
        ),
    )


@remedy("DATA-020", "fat-exfat")
def _data_020_fat(ctx: Ctx, out: Outcome) -> Fix:
    """Prefer a journaling filesystem."""
    return Fix(
        "Use a journaling filesystem",
        (
            manual(
                "Choose a folder on an NTFS, APFS or ext4 volume and set SADI_DATA_ROOT to it.",
                "The doctor reports a journaling filesystem.",
                mutates=Mutates.DATA_DIR,
                changes="Changes which folder holds new sessions; existing sessions are not moved.",
                if_not="Reformatting a drive erases it; copy files off first.",
            ),
        ),
    )


@check(
    "DATA-030",
    Layer.DATA,
    "Free space",
    Severity.BLOCKER,
    {
        "below-minimum": "Under 2 GiB free: acquisition would refuse to start",
        "low": "Under 10 GiB free",
    },
    "shutil.disk_usage of the nearest existing parent of the data root",
)
def data_030(ctx: Ctx) -> Outcome:
    """Compare free bytes with the store's minimum."""
    root = _root(ctx)
    free = ctx.probes.disk_free(root)
    if free is None:
        return skip(SkipReason.TOOL_MISSING, "Could not read disk usage", root=root)
    gib = round(free / GIB, 1)
    if free < MIN_FREE_BYTES:
        return fail("below-minimum", f"Only {gib} GiB free", free_bytes=free)
    if free < LOW_FREE_BYTES:
        return warn("low", f"{gib} GiB free; consider freeing space", free_bytes=free)
    return ok(f"{gib} GiB free", free_bytes=free)


def _free_space_fix(ctx: Ctx) -> Fix:
    """Shared free-space remedy."""
    root = _root(ctx)
    show = "Get-PSDrive -PSProvider FileSystem" if ctx.os is Os.WINDOWS else f"df -h '{root}'"
    return Fix(
        "Free disk space",
        (
            action(
                "Show free space on the data volume.",
                "The Avail/Free column shows the current free space.",
                cmd(ctx.os, show),
            ),
            manual(
                "Delete files you no longer need from this disk, or point SADI_DATA_ROOT at a bigger disk. Do not delete SADI session folders.",
                "At least 10 GiB is free.",
            ),
        ),
    )


@remedy("DATA-030", "below-minimum")
def _data_030_min(ctx: Ctx, out: Outcome) -> Fix:
    """Free space (blocker)."""
    return _free_space_fix(ctx)


@remedy("DATA-030", "low")
def _data_030_low(ctx: Ctx, out: Outcome) -> Fix:
    """Free space (warning)."""
    return _free_space_fix(ctx)


@check(
    "DATA-090",
    Layer.DATA,
    "Emergency spill files",
    Severity.WARNING,
    {"spill-present": "Unimported emergency spill files exist"},
    "spill files in <root>/spill, the per-user spill dir and the OS temp dir",
)
def data_090(ctx: Ctx) -> Outcome:
    """Warn when an earlier crash left spill files behind."""
    files = ctx.probes.spill_files(_root(ctx))
    if files:
        return warn("spill-present", f"{len(files)} spill file(s) await import", files=files)
    return ok("No spill files")


@remedy("DATA-090", "spill-present")
def _data_090_spill(ctx: Ctx, out: Outcome) -> Fix:
    """Import through the app; the doctor never touches data."""
    return Fix(
        "Import the spilled data",
        (
            manual(
                "Start SADI and use the import prompt for the listed spill files.",
                "SADI shows the recovered session and the spill files are marked imported.",
                mutates=Mutates.DATA,
                changes="Creates a recovered session from the spill files; the spill files are kept until you confirm.",
                if_not="Keep the files; do not delete them until the import succeeds.",
            ),
        ),
    )


@check(
    "DATA-040",
    Layer.DATA,
    "Flush primitive works on this volume",
    Severity.BLOCKER,
    {
        "fsync-unsupported": "fsync fails on the data volume",
        "fullfsync-fallback": "macOS F_FULLFSYNC is unavailable; fsync alone may not reach the disk",
        "fsync-slow": "Median flush is over 200 ms (HDD, USB stick or antivirus)",
    },
    "creates, fsyncs 5 times and deletes one file under <root>/doctor/ (needs --allow-probe-write)",
    depends_on=("DATA-010",),
    opt_in_flag="allow_probe_write",
)
def data_040(ctx: Ctx) -> Outcome:
    """Measure fsync on the data volume with one throwaway probe file."""
    facts = ctx.probes.flush_facts(_root(ctx))
    info = {"p50_ms": facts.p50_ms, "fullfsync": facts.fullfsync}
    if facts.status == "unsupported":
        return fail("fsync-unsupported", f"fsync failed: {facts.detail}", **info)
    if facts.status == "error":
        return skip(SkipReason.TOOL_MISSING, f"Probe file could not be used: {facts.detail}")
    if ctx.os is Os.MACOS and facts.fullfsync is False:
        return warn("fullfsync-fallback", "F_FULLFSYNC is not supported here", **info)
    if facts.p50_ms > SLOW_FSYNC_MS:
        return warn("fsync-slow", f"Median flush takes {facts.p50_ms:.0f} ms", **info)
    return ok(f"Median flush takes {facts.p50_ms:.1f} ms", **info)


@remedy("DATA-040", "fsync-unsupported")
def _data_040_unsupported(ctx: Ctx, out: Outcome) -> Fix:
    """Move to a filesystem with working flushes."""
    return Fix(
        "Use a filesystem with a working flush",
        (
            manual(
                "Choose a folder on a local ext4, NTFS or APFS volume and set SADI_DATA_ROOT to it.",
                "The doctor reports a median flush time.",
                mutates=Mutates.DATA_DIR,
                changes="Changes which folder holds new sessions; existing sessions are not moved.",
            ),
        ),
    )


@remedy("DATA-040", "fullfsync-fallback")
def _data_040_fullfsync(ctx: Ctx, out: Outcome) -> Fix:
    """Explain the macOS volume limitation."""
    return Fix(
        "Use an APFS or HFS+ volume",
        (
            manual(
                "Put the data folder on the internal APFS disk; some external and network volumes cannot honour a full flush.",
                "The doctor reports F_FULLFSYNC support.",
                mutates=Mutates.DATA_DIR,
                changes="Changes which folder holds new sessions; existing sessions are not moved.",
            ),
        ),
    )


@remedy("DATA-040", "fsync-slow")
def _data_040_slow(ctx: Ctx, out: Outcome) -> Fix:
    """Suggest a faster disk or an antivirus exclusion."""
    return Fix(
        "Use a faster disk",
        (
            manual(
                "Move the data folder to an internal SSD; on Windows also exclude it from antivirus (see DATA-060).",
                "The median flush is under 200 ms.",
                mutates=Mutates.DATA_DIR,
                changes="Changes which folder holds new sessions; existing sessions are not moved.",
                if_not="USB sticks and spinning disks are often slower than 200 ms.",
            ),
        ),
    )


def _under(root: str, name: str) -> str:
    """Join name onto root with a forward slash, ignoring a trailing separator."""
    return root.rstrip("/\\") + "/" + name


def _lock_target(ctx: Ctx) -> str | None:
    """Return an existing file or directory under the root to take a read-only lock on."""
    root = _root(ctx)
    for name in (CONFIG_FILE, "sessions"):
        path = _under(root, name)
        if ctx.probes.exists(path):
            return path
    return None


@check(
    "DATA-050",
    Layer.DATA,
    "Lock primitive works on this volume",
    Severity.BLOCKER,
    {
        "locks-unsupported": "File locking is not supported on the data volume",
        "lock-held-by-other": "The probe target is locked: another SADI is running",
    },
    "non-blocking shared lock on a read-only descriptor of <root>/config.toml or <root>/sessions",
    depends_on=("DATA-010",),
)
def data_050(ctx: Ctx) -> Outcome:
    """Take and release a shared lock on an existing entry under the root."""
    target = _lock_target(ctx)
    if target is None:
        return skip(SkipReason.UNVERIFIED, "No config.toml or sessions/ under the root to lock")
    state = ctx.probes.lock_state(target)
    if state == "unsupported":
        return fail("locks-unsupported", f"Locking fails on {target}", target=target)
    if state == "held":
        return warn("lock-held-by-other", f"{target} is locked by another process", target=target)
    if state == "error":
        return skip(SkipReason.TOOL_MISSING, f"Could not open {target} for the lock probe")
    return ok(f"Locking works on {target}", target=target)


@remedy("DATA-050", "locks-unsupported")
def _data_050_unsupported(ctx: Ctx, out: Outcome) -> Fix:
    """Move off a volume without locks."""
    root = _root(ctx)
    show = "Get-PSDrive -PSProvider FileSystem" if ctx.os is Os.WINDOWS else f"df -T '{root}'"
    return Fix(
        "Use a local filesystem with locking",
        (
            action(
                "Show which filesystem holds the data folder.",
                "The type is a network or exotic filesystem.",
                cmd(ctx.os, show),
            ),
            manual(
                "Set SADI_DATA_ROOT to a folder on a local disk (WSL: inside the Linux home, not /mnt/c).",
                "The doctor reports that locking works.",
                mutates=Mutates.DATA_DIR,
                changes="Changes which folder holds new sessions; existing sessions are not moved.",
            ),
        ),
    )


@remedy("DATA-050", "lock-held-by-other")
def _data_050_held(ctx: Ctx, out: Outcome) -> Fix:
    """Another SADI holds the lock; nothing is broken."""
    return Fix(
        "Close the other SADI",
        (
            manual(
                "Another SADI instance is using this data folder. Close it, or use a different data folder for this one.",
                "The doctor reports that locking works.",
                if_not="Do not delete lock files by hand.",
            ),
        ),
    )


@check(
    "DATA-060",
    Layer.DATA,
    "Antivirus or indexer interference",
    Severity.WARNING,
    {
        "not-excluded-from-defender": "Windows Defender scans the data root (no exclusion)",
        "indexer-scans-root": "Spotlight indexes the volume holding the data root",
        "sharing-violations-logged": "Logs mention DurableSharingViolation in the data root",
    },
    "Get-MpPreference ExclusionPath (Windows); mdutil -s <root> (macOS); DurableSharingViolation in <root>/logs",
    applies_to=frozenset({Os.WINDOWS, Os.MACOS}),
)
def data_060(ctx: Ctx) -> Outcome:
    """Look for scanners that hold files open and break durable renames."""
    root = _root(ctx)
    logs = _log_files(ctx)
    hits = sum((ctx.probes.read_text(f) or "").count(SHARING_MARK) for f in logs)
    if hits:
        return warn(
            "sharing-violations-logged", f"{hits} sharing violation(s) in the logs", count=hits
        )
    if ctx.os is Os.WINDOWS:
        res = ctx.probes.run(EXCLUSIONS_PS)
        if res.is_err or res.unwrap().exit_code != 0:
            return skip(SkipReason.TOOL_MISSING, "Could not read the Defender exclusions")
        lines = [x.strip().lower().rstrip("\\") for x in res.unwrap().stdout_tail.splitlines()]
        low = root.lower().rstrip("\\")
        if not any(x and (low == x or low.startswith(x + "\\")) for x in lines):
            return warn(
                "not-excluded-from-defender",
                "The data root is not excluded from Defender",
                root=root,
            )
        return ok("The data root is excluded from Defender", root=root)
    res = ctx.probes.run(("mdutil", "-s", root))
    if res.is_err or res.unwrap().exit_code != 0:
        return skip(SkipReason.TOOL_MISSING, "Could not read the Spotlight state")
    if "indexing enabled" in res.unwrap().stdout_tail.lower():
        return warn("indexer-scans-root", "Spotlight indexes this volume", root=root)
    return ok("Spotlight does not index this volume", root=root)


@remedy("DATA-060", "not-excluded-from-defender")
def _data_060_defender(ctx: Ctx, out: Outcome) -> Fix:
    """Exclude the root from Defender (done by the user, never the doctor)."""
    root = _root(ctx)
    return Fix(
        "Exclude the data folder from Defender",
        (
            action(
                "In an administrator PowerShell, add the exclusion.",
                "No output.",
                cmd(ctx.os, f"Add-MpPreference -ExclusionPath '{root}'"),
                mutates=Mutates.SYSTEM,
                changes="Defender stops scanning the data folder.",
                if_not="Group policy may block it; ask your administrator.",
            ),
        ),
    )


@remedy("DATA-060", "indexer-scans-root")
def _data_060_indexer(ctx: Ctx, out: Outcome) -> Fix:
    """Keep the indexer out of the data folder."""
    root = _root(ctx)
    return Fix(
        "Keep the indexer away from the data folder",
        (
            manual(
                f"Open System Settings, Siri & Spotlight, Spotlight Privacy, and add {root}.",
                "mdutil no longer reports indexing for the folder.",
                mutates=Mutates.SYSTEM,
                changes="Spotlight stops indexing the data folder.",
            ),
        ),
    )


@remedy("DATA-060", "sharing-violations-logged")
def _data_060_sharing(ctx: Ctx, out: Outcome) -> Fix:
    """Find the scanner holding files open."""
    root = _root(ctx)
    if ctx.os is Os.WINDOWS:
        step = action(
            "Exclude the data folder from Defender (administrator PowerShell).",
            "No output.",
            cmd(ctx.os, f"Add-MpPreference -ExclusionPath '{root}'"),
            mutates=Mutates.SYSTEM,
            changes="Defender stops scanning the data folder.",
            if_not="Also exclude it from third-party antivirus and backup tools.",
        )
    else:
        step = manual(
            "Exclude the data folder from Spotlight, Time Machine and any antivirus.",
            "No new sharing violations appear in the logs.",
            mutates=Mutates.SYSTEM,
            changes="Background tools stop touching the data folder.",
        )
    return Fix("Stop scanners from holding session files", (step,))


@check(
    "DATA-070",
    Layer.DATA,
    "Config file parses",
    Severity.BLOCKER,
    {"syntax-error": "config.toml is not valid TOML (line and column given)"},
    "tomllib parse of <root>/config.toml; no pydantic Config model exists yet, so values are not validated",
    depends_on=("DATA-010",),
)
def data_070(ctx: Ctx) -> Outcome:
    """Parse the optional config file as TOML."""
    path = _under(_root(ctx), CONFIG_FILE)
    if not ctx.probes.exists(path):
        return ok("No config file; defaults apply", path=path)
    text = ctx.probes.read_text(path)
    if text is None:
        return skip(SkipReason.TOOL_MISSING, f"Could not read {path}", path=path)
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        return fail("syntax-error", f"{path}: {exc}", path=path)
    return ok(f"{path} parses", path=path)


@remedy("DATA-070", "syntax-error")
def _data_070_syntax(ctx: Ctx, out: Outcome) -> Fix:
    """Fix or set aside the file; the doctor never edits it."""
    return Fix(
        "Fix the config file",
        (
            manual(
                "Open config.toml in the data folder and fix the line named above, or rename it to config.toml.bad to use defaults.",
                "The doctor reports that the file parses.",
                mutates=Mutates.DATA_DIR,
                changes="Edits or renames config.toml.",
                if_not="Rename it and start SADI to regenerate a clean file.",
            ),
        ),
    )


def _log_files(ctx: Ctx) -> list[str]:
    """Return full paths of the files in <root>/logs (empty when absent)."""
    logs = _under(_root(ctx), LOG_DIR)
    return [f"{logs}/{n}" for n in ctx.probes.listdir(logs) or []]


@check(
    "DATA-080",
    Layer.DATA,
    "Log directory writable and log size",
    Severity.WARNING,
    {
        "not-writable": "The log directory is not writable",
        "oversized": "Log files total more than 1 GiB",
    },
    "os.access and total file size of <root>/logs (SADI writes no log files yet: absent is a pass)",
    depends_on=("DATA-010",),
)
def data_080(ctx: Ctx) -> Outcome:
    """Check the log directory is usable and not huge."""
    logs = _under(_root(ctx), LOG_DIR)
    if not ctx.probes.is_dir(logs):
        return ok("No log directory yet", path=logs)
    if not ctx.probes.writable(logs):
        return warn("not-writable", f"{logs} is not writable", path=logs)
    total = sum(ctx.probes.file_size(f) or 0 for f in _log_files(ctx))
    if total > LOG_LIMIT_BYTES:
        return warn("oversized", f"Logs use {round(total / GIB, 1)} GiB", total_bytes=total)
    return ok(f"Logs use {round(total / GIB, 2)} GiB", total_bytes=total)


@remedy("DATA-080", "not-writable")
def _data_080_perm(ctx: Ctx, out: Outcome) -> Fix:
    """Show ownership of the log directory."""
    logs = f"{_root(ctx)}/{LOG_DIR}"
    show = f"icacls '{logs}'" if ctx.os is Os.WINDOWS else f"ls -ld '{logs}'"
    return Fix(
        "Make the log folder writable",
        (
            action("Show who owns the folder.", "Your user can write to it.", cmd(ctx.os, show)),
            manual(
                "Fix the ownership, or remove the folder if it is empty and let SADI recreate it.",
                "The doctor reports the folder as writable.",
                mutates=Mutates.SYSTEM,
                changes="Changes folder permissions.",
            ),
        ),
    )


@remedy("DATA-080", "oversized")
def _data_080_big(ctx: Ctx, out: Outcome) -> Fix:
    """Suggest pruning old logs."""
    logs = f"{_root(ctx)}/{LOG_DIR}"
    show = (
        f"Get-ChildItem '{logs}' | Sort-Object Length -Descending | Select-Object -First 5 Name,Length"
        if ctx.os is Os.WINDOWS
        else f"ls -lS '{logs}' | head -n 6"
    )
    return Fix(
        "Prune old logs",
        (
            action("List the biggest log files.", "A short list of files.", cmd(ctx.os, show)),
            manual(
                "Delete the old rotated logs you no longer need, or lower the log retention setting.",
                "Logs use under 1 GiB.",
                mutates=Mutates.SYSTEM,
                changes="Deletes old log files.",
            ),
        ),
    )
