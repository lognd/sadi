# Publishing checklist
Status: draft

Course-specific lab material (reference lab VI, lab data, transcripts) is kept
out of git: `python/tests/fixtures/real_fp/` and `labview/` are gitignored and
the tracked docs and tickets use generic wording.

History was squashed into a single fresh import, so no earlier commit holds
the removed data or wording. A full backup of the previous private history
lives outside the repository; never push it anywhere public.

Before making the repository public:

1. Run `git log --all -S<term>` for each removed term; expect no hits.
2. Run `frob check` and the test suite from a clean clone.
3. Review `git ls-files` for anything course-specific.
4. Push to a new remote only after review.

Final-project material (weight and height inventory, weight sequencing and the
GP selector, with their tests and design docs) lives in the gitignored
`private/` directory (`private/final-project/`) and is never committed. Tracked
code and docs must not import from or link into `private/`.
