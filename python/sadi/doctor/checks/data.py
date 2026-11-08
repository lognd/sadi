"""DATA checks: data root location, filesystem, space, spill files."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from sadi.doctor.registry import Ctx, Fix, Outcome, check, fail, ok, remedy, skip, warn
from sadi.doctor.schema import Layer, Mutates, Os, Severity, SkipReason
from sadi.doctor.steps import action, cmd, manual

GIB = 1024**3
MIN_FREE_BYTES = 2 * GIB
LOW_FREE_BYTES = 10 * GIB
_NETWORK_FS = {"nfs", "nfs4", "cifs", "smb3", "smbfs", "sshfs", "fuse.sshfs", "fuse.rclone", "afs"}
_FAT_FS = {"vfat", "exfat", "msdos", "fat32"}
_DRVFS = {"9p", "drvfs"}


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
    """Point to the Setup screen; the doctor never creates the data root."""
    root = _root(ctx)
    return Fix(
        "Create the data root from SADI",
        (
            manual(
                f"Start SADI and accept or choose the data folder on the Setup screen ({root}).",
                "SADI creates the folder and shows the main screen.",
                mutates=Mutates.DATA_DIR,
                changes=f"Creates the data folder {root}.",
                if_not="Choose a folder on a local, writable disk.",
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
    "filesystem type of the longest matching mount in /proc/mounts (Linux/WSL)",
)
def data_020(ctx: Ctx) -> Outcome:
    """Reject filesystems where fsync or locks are unreliable."""
    if ctx.os in (Os.WINDOWS, Os.MACOS):
        return skip(SkipReason.UNVERIFIED, "Filesystem type probe is not implemented on this OS")
    root = _root(ctx)
    fs = ctx.probes.fstype(root)
    if fs is None:
        return skip(SkipReason.TOOL_MISSING, "Could not read /proc/mounts", root=root)
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
