# Results/Export screen

Status: current

Parent: [web layout](../web-layout.md), next to the [guidance panel](guidance.md). Server side:
[export](../server/export.md) and [results](../server/results.md).

- `screens/export/ExportScreen.tsx`: loads `GET /api/results` and `GET /api/export` (injectable
  fetcher) and renders the report, the format list and any error.
- Report (`ReportView`): final values as a table (display string, 95 % interval, plain-language
  confidence, MC cross-check state), pending quantities, and the result `notes` and `refinement`
  lines (free text).
  `ProvenanceTable` renders the `provenance` field of `GET /api/results`: per quantity, the point ids,
  the sample span (first to last, a dash when absent) and the algorithm. It is hidden while the
  list is empty (the lctt recompute is a stub).
- Formats (`FormatList`): download formats (CSV, the 32-column schema) are plain links to
  `GET /api/export/{id}`. Figure formats (inline JSON) get PNG and SVG buttons plus a DPI
  selector; `exportFigureFormat` fetches the figure data and renders it with the shared
  `plots/core` `exportFigure` (no new plot code), then saves the blob.
- Empty list (the lctt lab declares none yet): a "declares no export formats" message.
- Errors are problem+json: `toProblem` reads `title`, `detail` and `hint`; `ProblemAlert`
  shows them with `role="alert"`.
- Figure JSON carries no theme; the light publication theme is applied before drawing.

See also the [synthetic data banner](synthetic-banner.md) shown above the report and the download list.

## Provenance (Audit1 #36)

The report states the data source (real measurement or SYNTHETIC) in plain words. The provenance table shows a point count (ids in the tooltip), hides empty 0-to-0 sample spans, and uses readable quantity names.

## Download and close (~W5M4P7D)

The Download links fetch the file with `fetch()` instead of following the link. A refusal (for example 422 NotReady) shows the problem detail and hint in the page; success saves the file and shows "Saved a copy in <path>" from the `X-SADI-Saved` header (or a warning when the header is `failed`).

The header of every wizard screen has **Close session**, and the finished screen has **Start another session**. Both ask for confirmation, state that captured data stays saved in the session folder, then POST `/api/session/close` and return to session setup.

## Download a closed session (~VBQ0A3E)

Session setup shows a **Download** button next to Resume for each closed session. It fetches the CSV through the read-only `GET /api/sessions/{name}/export/{format_id}` (no new version, no device needed) and saves it; a refusal shows the problem detail and hint in the page.
