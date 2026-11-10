# Synthetic specimen source

Status: current

A simulated 32 AWG copper wire so the whole lab can be exercised end to
end without hardware. It is opt-in, loudly labelled, and can never be
mistaken for real data.

## Usage

Both an explicit flag and a typed confirmation phrase are required:

    sadi --synthetic-specimen --i-understand-this-is-fake="I UNDERSTAND THIS DATA IS SIMULATED"

If the phrase is omitted and stdin is a terminal, the launcher prompts for
it. Environment variables never enable the source. Combining it with
`--sim` or `--ad3` is a usage error, as is a wrong or missing phrase.

## Physics model

- Elastic region: E about 110 GPa, linear to an onset near 60 MPa.
- Yield and strain hardening: Voce saturation towards about 132 MPa.
- Creep under hold: logarithmic in time at constant load.
- Noise: seeded Gaussian, so output is deterministic per seed.
- Channels: LVDT on ACH0, load cell on ACH2.

## Safeguards

- Flag plus typed phrase; never default, never env-only.
- A `SYNTHETIC` marker file in the session directory, mirrored in the
  manifest (`synthetic: true`). `session_is_synthetic` is true if EITHER says so, so
  losing the marker (copy tools, sync) never relabels the data as real.
- `sadi serve --sim` (built-in simulator device) is treated the same way: the launcher
  serves in synthetic mode, so its sessions and exports are labelled SYNTHETIC.
- Resuming a session with a mismatched provenance is refused (HTTP 409,
  `ProvenanceMismatch`); real and synthetic data are never mixed.
- A `provenance` field on health, session, plot, results, modulus-fit
  payloads and the websocket hello and state messages.
- Setup session list shows a SYNTHETIC badge per synthetic session.
- A closed-session export that read only the verified prefix (torn tail) also gets a
  `RECOVERED-` filename prefix (placed before `SYNTHETIC-`, never duplicated) and a
  leading `# RECOVERED:` comment line (CSV) or `recovered` key (JSON).
- Exports get a `SYNTHETIC-` filename prefix, an `X-Sadi-Provenance`
  header, and a stamp in the body (CSV comment lines, JSON key).
- A banner at launch.

## Scenario generator

`sadi.synthetic.generate_scenario(seed, flags)` returns a `Scenario` with
its `Truth`. It randomizes LVDT calibration, mass sequences (some
duplicated, some out of order), mass uncertainty, tare, clamp-slip
cycles, a long elastic run, a short plastic run past yield, and settle
behaviour per load step. Faults (dropped frames, saturation, spike) are
off unless set explicitly in `ScenarioFlags`.

## Driver

`sadi.synthetic.driver.drive_lab` runs the whole wizard through the HTTP
API, then reads E and yield from the server's own `/api/results` and
compares them to ground truth; `analyse` is only an independent refit that
is cross-checked and reported (`local_e_pa`, `local_yield_pa`). A quantity the
server did not report is listed in `DriveReport.missing`, never back-filled.
Faulty points are excluded through the server (the id is resolved from the
committed seq), a failed run stops the replay, and the uncertainty library's
per-value logging is silenced during a replay. Tolerances:
E 6 percent (`TOL_E`), yield 5 percent (`TOL_YIELD`), calibration slope
1 percent (`TOL_CAL_SLOPE`).

## Unknown provenance (orphan spill imports)

- A spill imported with no parent session has no known origin. Its manifest sets
  `provenance_unknown: true` (default false, so old manifests still load) and
  `synthetic: false`: it is neither real nor synthetic.
- `DataProvenance.source` is `"unknown"` (label `PROVENANCE UNKNOWN`). Closed-session
  exports get an `UNKNOWN-` filename prefix, `X-Sadi-Provenance: unknown`, and a stamp
  in the body. The setup list shows a "Provenance unknown" badge.
- Children (resume, spill join) of an unknown session stay unknown.
