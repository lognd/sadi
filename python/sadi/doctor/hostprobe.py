"""Host probes for the platform and browser checks: pure parsers plus thin OS readers."""

# frob:ticket 01M6WJHVZC0JYPV6W1CCFWSS8S
from __future__ import annotations

import json
import re
import socket
import sys
import webbrowser
from pathlib import Path

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

_MOUNT_RE = re.compile(r"^\S.* on (?P<mount>/.*?) \((?P<fs>[^,)]+)")
_VERSION_RE = re.compile(r"(\d+)(?:\.\d+)*")
_FAMILIES = (
    ("firefox", "firefox"),
    ("chrome", "chromium"),
    ("chromium", "chromium"),
    ("edge", "chromium"),
    ("brave", "chromium"),
    ("safari", "safari"),
)
_WIN_VERSION_KEYS = {
    "firefox": (r"SOFTWARE\Mozilla\Mozilla Firefox", "CurrentVersion"),
    "chromium": (r"SOFTWARE\Google\Chrome\BLBeacon", "version"),
}
_FSTYPE_BY_WIN_NAME = {"fat": "fat32"}
_DRIVE_REMOTE = 4


def family_of(name: str) -> str | None:
    """Map a browser binary, app or ProgId name to firefox, chromium or safari, else None."""
    low = name.lower()
    for needle, family in _FAMILIES:
        if needle in low:
            return family
    return None


def major_version(text: str) -> int | None:
    """Return the first dotted number's major part in text, or None."""
    match = _VERSION_RE.search(text)
    return int(match.group(1)) if match else None


def mount_fstype(mount_output: str, real: str) -> str | None:
    """Return the longest-prefix mount's fstype from macOS `mount` output, else None."""
    best: tuple[int, str] | None = None
    for line in mount_output.splitlines():
        match = _MOUNT_RE.match(line)
        if not match:
            continue
        mount = match["mount"]
        if (real == mount or real.startswith(mount.rstrip("/") + "/")) and (
            best is None or len(mount) > best[0]
        ):
            best = (len(mount), match["fs"].lower())
    return best[1] if best else None


def windows_fstype(path: str) -> str | None:
    """Return the Windows volume filesystem name (ntfs, fat32, smbfs...) for path, else None."""
    if sys.platform != "win32":
        return None
    import ctypes

    root = Path(path).resolve().anchor
    if not root:
        return None
    kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]
    if root.startswith("\\\\") or kernel.GetDriveTypeW(root) == _DRIVE_REMOTE:
        return "smbfs"
    buf = ctypes.create_unicode_buffer(32)
    if not kernel.GetVolumeInformationW(root, None, 0, None, None, None, buf, 32):
        _log.debug("GetVolumeInformationW failed for %s", root)
        return None
    name = buf.value.lower()
    return _FSTYPE_BY_WIN_NAME.get(name, name)


def windows_long_paths() -> bool | None:
    """Return LongPathsEnabled from the registry on Windows, else None."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem"
        ) as key:
            value, _ = winreg.QueryValueEx(key, "LongPathsEnabled")
    except OSError:
        return False
    return bool(value)


def windows_default_browser() -> tuple[str, int] | None:
    """Return (family, major) of the Windows default browser from the registry, else None."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice",
        ) as key:
            prog_id = str(winreg.QueryValueEx(key, "ProgId")[0])
    except OSError:
        return None
    family = family_of(prog_id)
    if family not in _WIN_VERSION_KEYS:
        return None
    sub, name = _WIN_VERSION_KEYS[family]
    for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        try:
            with winreg.OpenKey(hive, sub) as key:
                major = major_version(str(winreg.QueryValueEx(key, name)[0]))
        except OSError:
            continue
        if major is not None:
            return family, major
    return None


def web_bundle_version() -> str | None:
    """Return the `sadi` field of sadi/web/dist/version.json, or None when absent or bad."""
    path = Path(__file__).resolve().parent.parent / "web" / "dist" / "version.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    value = data.get("sadi") if isinstance(data, dict) else None
    return value if isinstance(value, str) else None


def build_target() -> str | None:
    """Return sadi_py.BUILD_TARGET when the extension exposes it, else None."""
    try:
        import sadi_py  # type: ignore[import-not-found]
    except ImportError:
        return None
    value = getattr(sadi_py, "BUILD_TARGET", None)
    return value if isinstance(value, str) else None


def launch_hit(timeout: float) -> bool:
    """Open the default browser at a throwaway loopback listener; True if it fetched in time."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        srv.settimeout(timeout)
        url = f"http://127.0.0.1:{srv.getsockname()[1]}/doctor-ping"
        _log.info("launch dry run: opening %s", url)
        if not webbrowser.open(url):
            return False
        try:
            conn, _ = srv.accept()
        except OSError:
            return False
        with conn:
            conn.settimeout(1.0)
            try:
                conn.recv(1024)
                conn.sendall(b"HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nok")
            except OSError:
                _log.debug("dry run: browser connected but did not complete a request")
        return True
