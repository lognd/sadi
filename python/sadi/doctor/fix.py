"""`sadi doctor fix CHECK-ID`: dry-run by default; runs only confirmed, non-data fixable commands."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

import shlex
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass

from typani import Err, Ok, Result

from sadi.doctor import run
from sadi.doctor.probes import Probes
from sadi.doctor.schema import (
    CheckResult,
    Command,
    DoctorError,
    Mutates,
    RunOptions,
    Status,
    StepKind,
)
from sadi.logging_setup import get_logger

_log = get_logger(__name__)

EXIT_OK = 0
EXIT_STILL_BAD = 1
EXIT_DECLINED = 3
# data-dir (mkdir of the empty root) and install (UI build) only ever create; neither deletes or overwrites.
RUNNABLE = frozenset({Mutates.SYSTEM, Mutates.PROCESS, Mutates.DATA_DIR, Mutates.INSTALL})

__all__ = ["FixAction", "plan", "fix"]


@dataclass(frozen=True)
class FixAction:
    """One command the doctor is allowed to run, with its step number and mutation class."""

    step: int
    command: Command
    mutates: Mutates


def plan(result: CheckResult, data_root: str | None) -> list[FixAction]:
    """List the fixable commands of a result; `data` steps and commands touching an existing data root never qualify."""
    if result.remediation is None:
        return []
    actions = []
    for n, step in enumerate(result.remediation.steps, 1):
        if step.kind is StepKind.VERIFY or step.mutates not in RUNNABLE:
            continue
        for c in step.commands:
            if c.fixable and (
                step.mutates is Mutates.DATA_DIR or data_root is None or data_root not in c.line
            ):
                actions.append(FixAction(n, c, step.mutates))
    return actions


def _ask(prompt: str) -> bool:
    """Ask a yes/no question on the terminal; anything but y/yes is no."""
    sys.stdout.write(prompt)
    sys.stdout.flush()
    return sys.stdin.readline().strip().lower() in ("y", "yes")


def _exec(line: str) -> int:
    """Run one command line without a shell, output shown; return its exit code."""
    argv = shlex.split(line)
    _log.warning("fix: running %s", argv)
    return subprocess.run(argv, check=False).returncode  # noqa: S603


def fix(
    check_id: str,
    options: RunOptions,
    probes: Probes,
    out: Callable[[str], None],
    *,
    apply: bool = False,
    yes: bool = False,
    non_interactive: bool = False,
    ask: Callable[[str], bool] = _ask,
    execute: Callable[[str], int] = _exec,
    is_tty: bool | None = None,
) -> Result[int, DoctorError]:
    """Show the remediation for CHECK-ID; with `apply`, run confirmed fixable commands; return the exit code."""
    opts = options.model_copy(update={"checks": (check_id,), "skip": ()})
    first = run(opts, probes)
    if first.is_err:
        return Err(first.unwrap_err())
    report = first.unwrap()
    result = report.results[0]
    out(f"{result.id} {result.status.value}: {result.headline}\n")
    if result.status not in (Status.WARN, Status.FAIL):
        return Ok(EXIT_OK)
    actions = plan(result, report.host.data_root)
    steps = result.remediation.steps if result.remediation else ()
    for n, step in enumerate(steps, 1):
        out(f"Step {n} of {len(steps)}: {step.text}\n")
        for c in step.commands:
            tag = "[fixable]" if any(a.command is c for a in actions) else "[run it yourself]"
            out(f"    {c.line}  {tag}\n")
    if not apply:
        out("Dry run: nothing was changed. Re-run with --apply to run the [fixable] commands.\n")
        return Ok(EXIT_STILL_BAD)
    tty = sys.stdin.isatty() if is_tty is None else is_tty
    if yes and not tty and not non_interactive:
        out("--yes without a terminal needs --non-interactive; nothing was changed.\n")
        return Err(DoctorError.FixNeedsTerminal)
    if yes:
        _log.warning("fix: --yes given (non_interactive=%s)", non_interactive)
    if not actions:
        out("No fixable commands for this check; follow the steps above by hand.\n")
        return Ok(EXIT_STILL_BAD)
    for a in actions:
        out(f"Step {a.step} changes: {a.mutates.value}\n")
        if not (yes or ask(f"Run `{a.command.line}`? [y/N] ")):
            _log.info("fix: declined %s", a.command.line)
            out("Declined; nothing further was run.\n")
            return Ok(EXIT_DECLINED)
        code = execute(a.command.line)
        if code != 0:
            out(f"Command failed with exit code {code}; stopping.\n")
            return Ok(EXIT_STILL_BAD)
    again = run(opts, probes)
    if again.is_err:
        return Err(again.unwrap_err())
    after = again.unwrap().results[0]
    out(f"{after.id} {after.status.value}: {after.headline}\n")
    return Ok(EXIT_OK if after.status is Status.PASS else EXIT_STILL_BAD)
