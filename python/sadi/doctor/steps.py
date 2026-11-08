"""Step builders so every remediation reads the same and always ends with a verify step."""

# frob:ticket 01M6WA9WYE9D71BBA7AV3H5CGF
from __future__ import annotations

from sadi.doctor.schema import Command, Mutates, Os, Shell, Step, StepKind

DOCTOR_CMD = "sadi-doctor"


def shell_for(os: Os) -> Shell:
    """Return the shell a command for this OS is written in."""
    return Shell.POWERSHELL if os is Os.WINDOWS else Shell.SH


def cmd(os: Os, line: str, *, context: str | None = None, fixable: bool = False) -> Command:
    """Build one command line in the OS's native shell."""
    return Command(shell=shell_for(os), line=line, context=context, fixable=fixable)


def action(
    text: str,
    expect: str,
    *commands: Command,
    mutates: Mutates = Mutates.NONE,
    changes: str | None = None,
    if_not: str | None = None,
    alt: str | None = None,
) -> Step:
    """Build a step the user performs by running commands."""
    return Step(
        kind=StepKind.ACTION,
        text=text,
        commands=commands,
        expect=expect,
        mutates=mutates,
        changes=changes,
        if_not=if_not,
        alt=alt,
    )


def manual(
    text: str,
    expect: str,
    *,
    mutates: Mutates = Mutates.NONE,
    changes: str | None = None,
    if_not: str | None = None,
) -> Step:
    """Build a step done by hand (GUI, hardware, app action) with no command."""
    return Step(
        kind=StepKind.MANUAL,
        text=text,
        expect=expect,
        mutates=mutates,
        changes=changes,
        if_not=if_not,
    )


def verify(check_id: str, os: Os) -> Step:
    """Build the closing step that re-runs exactly this check."""
    return Step(
        kind=StepKind.VERIFY,
        text="Re-run this check to confirm the fix.",
        commands=(cmd(os, f"{DOCTOR_CMD} --check {check_id}"),),
        expect=f"{check_id} reports PASS.",
        if_not="Re-read the output above; the headline names what is still wrong.",
    )
