"""Ad3Guard vs real signals/uvicorn in a subprocess: one close, handlers restored."""

# frob:ticket 01M6Z5J0CK9PM3NFHKN84QQJAV
from __future__ import annotations

import signal
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

from typani import Ok

from sadi.bench.ad3 import Ad3Closed
from sadi.bench.ad3.fake import FakeDwf
from sadi.bench.ad3.launch import Ad3Guard, open_managed_ad3

_PRELUDE = """
import os, signal, sys
from typani import Ok
from sadi.bench.ad3 import Ad3Closed
from sadi.bench.ad3.fake import FakeDwf
from sadi.bench.ad3.launch import Ad3Guard, open_managed_ad3

class CountingDwf(FakeDwf):
    closes = 0
    def close(self, dev):
        CountingDwf.closes += 1
        print("CLOSE", flush=True)
        return super().close(dev)

def _ready():
    # Raw write, not print(): a SIGTERM that lands while print() still holds the stdout buffer
    # lock makes the handler's print("CLOSE") raise "reentrant call" and the close is lost.
    os.write(1, b"READY\\n")

guard = open_managed_ad3(lambda: Ok(Ad3Closed(CountingDwf()))).unwrap()
"""

_PLAIN = (
    _PRELUDE
    + """
_ready()
signal.pause()
"""
)

_UVICORN = (
    _PRELUDE
    + """
import threading, uvicorn
from fastapi import FastAPI
app = FastAPI()
cfg = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning")
server = uvicorn.Server(cfg)
orig = server.startup
async def startup(sockets=None):
    await orig(sockets)
    _ready()
server.startup = startup
try:
    server.run()
finally:
    guard.close()
"""
)


def _run_and_term(code: str, tmp_path: Path, sig: int) -> tuple[int, str]:
    script = tmp_path / "child.py"
    script.write_text(textwrap.dedent(code))
    proc = subprocess.Popen(
        [sys.executable, str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )
    assert proc.stdout is not None
    for line in proc.stdout:  # logging may share stdout; skip until the READY marker
        if line.strip() == "READY":
            break
    else:
        raise AssertionError("child never became READY")
    proc.send_signal(sig)
    try:
        out, _err = proc.communicate(timeout=20)
    except subprocess.TimeoutExpired:
        proc.kill()
        out, err = proc.communicate()
        raise AssertionError(f"child hung after signal {sig}: {out!r} {err!r}") from None
    assert proc.returncode is not None
    assert "reentrant call" not in _err, f"child stdout re-entered during signal: {_err!r}"
    return int(proc.returncode), out


# frob:tests python/sadi/bench/ad3/launch.py::Ad3Guard._on_signal
def test_sigterm_subprocess_single_close_exit_code(tmp_path: Path) -> None:
    """frob:tests sadi.bench.ad3.launch.Ad3Guard._on_signal"""
    code, out = _run_and_term(_PLAIN, tmp_path, signal.SIGTERM)
    assert out.splitlines().count("CLOSE") == 1
    assert code == 128 + signal.SIGTERM


def test_sigterm_with_uvicorn_single_close(tmp_path: Path) -> None:
    """frob:tests sadi.bench.ad3.launch.Ad3Guard.close"""
    code, out = _run_and_term(_UVICORN, tmp_path, signal.SIGTERM)
    assert out.splitlines().count("CLOSE") == 1
    assert code in (0, 128 + signal.SIGTERM)


def test_sighup_subprocess_single_close(tmp_path: Path) -> None:
    """frob:tests sadi.bench.ad3.launch.Ad3Guard.install_signal_handlers"""
    code, out = _run_and_term(_PLAIN, tmp_path, signal.SIGHUP)
    assert out.splitlines().count("CLOSE") == 1
    assert code == 128 + signal.SIGHUP


def _guard() -> Ad3Guard:
    return open_managed_ad3(lambda: Ok(Ad3Closed(FakeDwf()))).unwrap()


# frob:tests python/sadi/bench/ad3/launch.py::Ad3Guard._restore_signals
def test_prior_handlers_restored_on_close() -> None:
    """frob:tests sadi.bench.ad3.launch.Ad3Guard.close"""
    marker = signal.getsignal(signal.SIGTERM)
    guard = _guard()
    assert signal.getsignal(signal.SIGTERM) != marker
    guard.install_signal_handlers()  # idempotent
    guard.close()
    assert signal.getsignal(signal.SIGTERM) == marker


def test_handlers_not_installed_off_main_thread() -> None:
    """frob:tests sadi.bench.ad3.launch.Ad3Guard.install_signal_handlers"""
    fake = FakeDwf()
    session = Ad3Closed(fake).open().unwrap()
    guard = Ad3Guard(session)
    before = signal.getsignal(signal.SIGTERM)
    t = threading.Thread(target=guard.install_signal_handlers)
    t.start()
    t.join()
    assert signal.getsignal(signal.SIGTERM) == before
    guard.close()
