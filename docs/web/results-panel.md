# Results panel

Status: current

`web/src/components/results/ResultsPanel.tsx` is the always-visible live results panel
(ticket ~9PMPWH8). It is display only: the API (sig-fig formatter, see
[live-results](../lctt/live-results.md)) is the source of truth for formatting, and the panel
shows the pre-formatted `display` and `confidence` strings verbatim.

- Rows: calibration slope, intercept, tare, E, r^2, yield; each shows value +/- U, standard
  uncertainty, 95% interval and the plain-language confidence sentence. Uncomputed results show
  "pending".
- Props: `results` (a `ResultSet`, replaced after every captured point), optional
  `settleSource` (which settle value fed E) and an injected `copy` clipboard function.
- Rows whose RSS vs Monte Carlo check is `disagrees` are flagged.
- "Copy values" writes one line per result with units via `copyText()`.

Types in `web/src/components/results/types.ts` mirror `python/sadi/core/results.py`. No server
endpoint is called by the panel; the host screen supplies the `ResultSet`.
