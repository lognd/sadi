# Publishing checklist
Status: draft

Course-specific lab material (reference lab VI, lab data, transcripts) is kept
out of git: `python/tests/fixtures/real_fp/` and `labview/` are gitignored and
the tracked docs use generic wording.

Warning: git history STILL contains the old data (the former real_fp
fixtures and earlier doc wording). The repository must not be made public
until history is rewritten.

Planned approach:

1. Work on a fresh mirror clone, never the working repository.
2. Run `git filter-repo --invert-paths --path python/tests/fixtures/real_fp/`
   plus a `--replace-text` file for the course and VI names.
3. Verify with `git log --all -S<term>` for each removed term, then run
   `frob check` and the test suite on the rewritten clone.
4. Rewrite or drop the ticket event history that quotes the removed names
   (tickets/*/events is an audit trail; handle it deliberately).
5. Force-push to a new remote only after review; leases and worktrees are
   re-created afterwards.
