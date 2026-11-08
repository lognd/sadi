// frob:ticket 01M6W7RATGKGPEYSMC5H8WGMBV
// frob:accept COV001 because="covered by ExportScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useCallback, useEffect, useState } from "react";
import { getLogger } from "../../api/log";
import { exportFigure, lightTheme, validateDrawable, type Drawable, type ExportOptions } from "../../plots/core";
import { exportUrl, getExportFormats, getFigureData, getResults, toProblem } from "./api";
import type { ExportFormatView, Problem, ResultSet, ResultValue } from "./types";

const log = getLogger("screens.export");

/** PNG resolutions offered for figure export. */
export const DPI_CHOICES = [96, 192, 300, 600] as const;

/** Download file name for a figure export. */
export function figureFileName(formatId: string, fmt: ExportOptions["format"]): string {
  return `${formatId}.${fmt}`;
}

/** Save a blob through a temporary link; browser only. */
function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

/** Fetch a figure format and render it with the shared plot exporter; returns a Problem on failure. */
export async function exportFigureFormat(
  formatId: string,
  opts: ExportOptions,
  fetchImpl: typeof fetch = fetch,
  save: (blob: Blob, name: string) => void = saveBlob,
): Promise<Problem | null> {
  const r = await getFigureData(formatId, fetchImpl);
  if (!r.ok) return toProblem(r.error);
  // Wire JSON carries no theme; default to the light publication theme.
  const drawable = { theme: lightTheme, ...(r.value as object) } as Drawable;
  const v = validateDrawable(drawable);
  if (!v.ok) {
    log.warn("figure data invalid", { formatId });
    return { title: "Figure data cannot be drawn", detail: `format ${formatId}`, hint: "Report this export format to the lab author.", status: null };
  }
  const x = await exportFigure(drawable, opts);
  if (!x.ok) {
    log.error("figure export failed", { formatId, error: x.error });
    return { title: "Figure export failed", detail: x.error, hint: "Try SVG, or a lower DPI.", status: null };
  }
  save(x.value.blob, figureFileName(formatId, opts.format));
  log.info("figure exported", { formatId, format: opts.format, dpi: opts.dpi });
  return null;
}

/** One value as a report row: display text, interval and which MC state applies. */
export function ReportRow({ v }: { v: ResultValue }) {
  return (
    <tr data-testid={`result-${v.name}`}>
      <th scope="row">{v.name}</th>
      <td>{v.display}</td>
      <td>{`${String(v.low95)} to ${String(v.high95)} ${v.unit}`}</td>
      <td>{v.confidence}</td>
      <td>{v.mc.status}</td>
    </tr>
  );
}

/** Report of final values with 95 % intervals, plus pending items and provenance notes. */
export function ReportView({ results }: { results: ResultSet | null }) {
  if (results === null) return <section aria-label="Report"><p>No results yet.</p></section>;
  return (
    <section aria-label="Report">
      <h2>Report</h2>
      <p>{`Based on ${String(results.n_points)} points.`}</p>
      {results.values.length === 0 ? <p>No values computable yet.</p> : (
        <table>
          <caption>Final values</caption>
          <thead><tr><th scope="col">Quantity</th><th scope="col">Value</th><th scope="col">95 % interval</th><th scope="col">Confidence</th><th scope="col">MC check</th></tr></thead>
          <tbody>{results.values.map((v) => <ReportRow key={v.name} v={v} />)}</tbody>
        </table>
      )}
      {results.pending.length > 0 ? <p data-testid="pending">{`Pending: ${results.pending.join(", ")}`}</p> : null}
      {results.notes.length + results.refinement.length > 0 ? (
        <ul aria-label="Provenance notes" data-testid="notes">
          {[...results.notes, ...results.refinement].map((n) => <li key={n}>{n}</li>)}
        </ul>
      ) : null}
    </section>
  );
}

/** Problem banner showing title, detail and the server hint. */
export function ProblemAlert({ p }: { p: Problem }) {
  return (
    <div role="alert" data-testid="problem">
      <p>{p.title}{p.detail ? `: ${p.detail}` : ""}</p>
      {p.hint ? <p>{`Hint: ${p.hint}`}</p> : null}
    </div>
  );
}

/** List of formats: downloads are links, figure formats get PNG/SVG export buttons; empty list shows a message. */
export function FormatList(props: {
  formats: ExportFormatView[];
  dpi: number;
  onDpi?: (dpi: number) => void;
  onFigure?: (f: ExportFormatView, format: ExportOptions["format"]) => void;
}) {
  const { formats, dpi, onDpi, onFigure } = props;
  if (formats.length === 0) {
    return <section aria-label="Export formats"><p data-testid="no-formats">This lab declares no export formats yet.</p></section>;
  }
  return (
    <section aria-label="Export formats">
      <h2>Export</h2>
      <label>
        {"PNG resolution "}
        <select value={dpi} onChange={(e) => { onDpi?.(Number(e.target.value)); }}>
          {DPI_CHOICES.map((d) => <option key={d} value={d}>{`${String(d)} dpi`}</option>)}
        </select>
      </label>
      <ul>
        {formats.map((f) => (
          <li key={f.id} data-testid={`format-${f.id}`}>
            {f.download ? (
              <a href={exportUrl(f.id)} download>{`Download ${f.title}`}</a>
            ) : (
              <>
                <span>{f.title}</span>
                <button type="button" onClick={() => { onFigure?.(f, "png"); }}>{`Export ${f.title} as PNG`}</button>
                <button type="button" onClick={() => { onFigure?.(f, "svg"); }}>{`Export ${f.title} as SVG`}</button>
              </>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Results/Export screen: loads the report and format list, handles downloads and figure export. */
export function ExportScreen({ fetchImpl = fetch }: { fetchImpl?: typeof fetch }) {
  const [results, setResults] = useState<ResultSet | null>(null);
  const [formats, setFormats] = useState<ExportFormatView[]>([]);
  const [problem, setProblem] = useState<Problem | null>(null);
  const [dpi, setDpi] = useState<number>(300);

  useEffect(() => {
    const live = { current: true };
    void (async () => {
      const [r, f] = await Promise.all([getResults(fetchImpl), getExportFormats(fetchImpl)]);
      if (!live.current) return;
      if (r.ok) setResults(r.value); else { log.warn("results failed", { kind: r.error.kind }); setProblem(toProblem(r.error)); }
      if (f.ok) setFormats(f.value); else { log.warn("formats failed", { kind: f.error.kind }); setProblem((p) => p ?? toProblem(f.error)); }
    })();
    return () => { live.current = false; };
  }, [fetchImpl]);

  const onFigure = useCallback((f: ExportFormatView, format: ExportOptions["format"]) => {
    log.info("figure export requested", { id: f.id, format, dpi });
    void exportFigureFormat(f.id, { format, dpi }, fetchImpl).then(setProblem);
  }, [dpi, fetchImpl]);

  return (
    <main aria-label="Results and export">
      {problem ? <ProblemAlert p={problem} /> : null}
      <ReportView results={results} />
      <FormatList formats={formats} dpi={dpi} onDpi={setDpi} onFigure={onFigure} />
    </main>
  );
}
