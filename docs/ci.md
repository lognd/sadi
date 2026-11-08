# Continuous integration

Status: draft

`.github/workflows/ci.yml` runs on every pull request and on pushes to
`main`. Portability bugs (fsync/rename, paths, serial port names) must
fail early, so every job runs on `ubuntu-latest`, `windows-latest` and
`macos-latest` (`fail-fast: false`, so one OS failing does not hide the
others).

## Jobs and required-check names

GitHub reports matrix jobs as `<job name>`; these are the required checks
to configure in branch protection.

| Check name | Steps |
| --- | --- |
| `rust (ubuntu-latest)`, `rust (windows-latest)`, `rust (macos-latest)` | `cargo fmt --all --check`, `cargo clippy --workspace --all-targets -- -D warnings`, `cargo nextest run --workspace`, `cargo test --doc`; on Linux also clippy with the `udev` feature (installs `libudev-dev`) |
| `python (ubuntu-latest)`, `python (windows-latest)`, `python (macos-latest)` | `ruff check`, `ruff format --check`, `python -m typani.lint sadi`, typani collision check, `ty check`, `pytest` (all via `uv run`, in `python/`) |
| `web (ubuntu-latest)`, `web (windows-latest)`, `web (macos-latest)` | `npm ci`, `npm run lint` (eslint), `npm run typecheck` (tsc), `npm test` (vitest), `vite build` (in `web/`) |

### Planned required checks (separate workflows, not yet created)

- Crash-recovery job (ticket DS6): its own workflow file.
- End-to-end job (ticket T2): its own workflow file.

They are kept out of `ci.yml` because they are slow and have different
triggers. Add their check names here and to branch protection when the
workflows land.

## Typani collision check

The python job runs `tools/check_typani_collisions.py` (ticket 66MX8BW,
U6) only if that file exists. The step is guarded by a file-exists test
and prints a skip message until the script lands; no workflow change is
needed then.

## Caching

- Cargo: `Swatinem/rust-cache` (keyed on `Cargo.lock` and toolchain).
- uv: `astral-sh/setup-uv` with `enable-cache`, keyed on `python/uv.lock`.
- npm: `actions/setup-node` with `cache: npm`, keyed on
  `web/package-lock.json`.

## Notes

- The toolchain comes from `rust-toolchain.toml` (stable, rustfmt,
  clippy). The default `serial` feature does not need libudev; only the
  `udev` feature does, hence the Linux-only step.
- `cargo nextest` does not run doctests, so a separate `cargo test --doc`
  step covers them.
- The web steps call the scripts in `web/package.json` (`lint`,
  `typecheck`, `test`); `vite build` is run directly. If those scripts are
  renamed, update the workflow.
- The workflow cannot be run locally; it was validated only as YAML
  (and with actionlint where available). The first real run is on GitHub.
