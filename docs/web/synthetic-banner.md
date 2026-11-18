# Synthetic data banner

Status: current

Parent: [web layout](../web-layout.md). Backend stamp: `python/sadi/synthetic/provenance.py`
(`DataProvenance`, `SYNTHETIC_LABEL`, `EXPORT_PREFIX`).

- State: `state/provenance.ts` keeps one zustand store holding the latest `DataProvenance`.
  `useProvenancePoll` (mounted in `App`) reads `provenance` from `GET /api/health` every 5 s;
  `ExportScreen` also feeds in `data_provenance` from `GET /api/results`.
- Component: `components/provenance/SyntheticBanner.tsx` is the only banner. It renders nothing
  unless the stamp says synthetic, so real data never shows it. It is text (`SYNTHETIC DATA - NOT A
  MEASUREMENT`) plus a warning-triangle icon plus a hazard-stripe edge (never colour alone), with
  `role="status"` and `aria-live="polite"`. Colours come from `--synthetic-bg/--synthetic-fg`
  (red/white in light, bright red/near-black in dark), both above 4.5:1 contrast.
- Placement: inside `InstrumentBarView` (sticky, so on every page), the live trace card (compact),
  `ResultsPanel`, the review screen, and the export report and download list.
- Downloads: when synthetic, the download list shows the `SYNTHETIC-` prefix and
  `exportFilename` prefixes figure and F3 CSV saves (the backend already prefixes server-named
  files and sends `X-Sadi-Provenance`).
- Tests: `components/provenance/provenance.test.tsx` covers both states.
