"""Process-wide failpoint registry (data-safety section 11) for kill/fail-between-steps tests."""

from __future__ import annotations

import errno as _errno
import os
import random
import threading
import time
from dataclasses import dataclass, field

from sadi.logging_setup import get_logger

_log = get_logger(__name__)

ENV_VAR = "SADI_FAILPOINTS"
SEED_VAR = "SADI_FAILPOINT_SEED"


@dataclass
class _Rule:
    """One parsed failpoint rule: an action plus its firing schedule."""

    action: str
    once: bool = False
    nth: int | None = None
    prob: float | None = None
    hits: int = 0
    fired: bool = False


@dataclass
class _Registry:
    """Mutable registry state guarded by a lock."""

    rules: dict[str, _Rule] = field(default_factory=dict)
    loaded_env: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)
    rng: random.Random = field(default_factory=random.Random)


_REG = _Registry()


def _parse(spec: str) -> _Rule:
    """Parse an action string such as `once:error:28` or `nth:3:kill` into a rule."""
    rule = _Rule(action="")
    rest = spec
    while True:
        head, _, tail = rest.partition(":")
        if head == "once":
            rule.once = True
            rest = tail
        elif head == "nth":
            n, _, rest = tail.partition(":")
            rule.nth = int(n)
        elif head == "prob":
            p, _, rest = tail.partition(":")
            rule.prob = float(p)
        else:
            break
    rule.action = rest
    head = rest.partition(":")[0]
    if head not in {"kill", "abort", "sleep", "error"}:
        raise ValueError(f"unknown failpoint action: {spec!r}")
    return rule


def configure(spec: dict[str, str]) -> None:
    """Replace the registry with `{name: action}` rules (tests and the harness use this)."""
    with _REG.lock:
        _REG.rules = {name: _parse(action) for name, action in spec.items()}
        _REG.loaded_env = True
        seed = os.environ.get(SEED_VAR)
        _REG.rng = random.Random(int(seed)) if seed is not None else random.Random()
    _log.info("failpoints configured: %s", sorted(spec))


def clear() -> None:
    """Remove every rule and re-arm lazy environment loading."""
    with _REG.lock:
        _REG.rules = {}
        _REG.loaded_env = False
    _log.debug("failpoints cleared")


def _load_env() -> None:
    """Load `SADI_FAILPOINTS` once; caller holds no lock."""
    raw = os.environ.get(ENV_VAR, "")
    spec = {}
    for item in filter(None, (p.strip() for p in raw.split(","))):
        name, _, action = item.partition("=")
        spec[name] = action
    if spec:
        configure(spec)
    else:
        with _REG.lock:
            _REG.loaded_env = True


def _should_fire(rule: _Rule) -> bool:
    """Advance the hit counter and decide whether the action fires now."""
    rule.hits += 1
    if rule.once and rule.fired:
        return False
    if rule.nth is not None and rule.hits != rule.nth:
        return False
    if rule.prob is not None and _REG.rng.random() >= rule.prob:
        return False
    return True


def failpoint(name: str) -> None:
    """Hit the named failpoint: a no-op unless a rule is armed; may kill, sleep or raise OSError."""
    if not _REG.loaded_env:
        _load_env()
    if not _REG.rules:
        return
    with _REG.lock:
        rule = _REG.rules.get(name)
        if rule is None:
            return
        fire = _should_fire(rule)
        hits = rule.hits
        if fire:
            rule.fired = True
    _log.debug("failpoint %s hit #%d fire=%s", name, hits, fire)
    if not fire:
        return
    _log.warning("failpoint %s firing action %s", name, rule.action)
    kind, _, arg = rule.action.partition(":")
    if kind == "kill":
        os._exit(137)
        return
    if kind == "abort":
        os.abort()
        return
    if kind == "sleep":
        time.sleep(int(arg) / 1000.0)
        return
    code = int(arg)
    raise OSError(code, f"failpoint {name}: {_errno.errorcode.get(code, 'error')}")
