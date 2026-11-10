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
