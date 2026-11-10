// frob:ticket 01M6WVTVH19EXW341V5K8SM7Z4
// frob:ticket 01M6W7RATGKGPEYSMC5H8WGMBV
// frob:ticket 01M6X7JNY6ZKZKDFRM3935NES4
// frob:accept COV001 because="covered by ExportScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
import { useCallback, useEffect, useState } from "react";
import { getLogger } from "../../api/log";
import { exportFigure, validateDrawable, type ExportOptions } from "../../plots/core";
import { SyntheticBanner } from "../../components/provenance/SyntheticBanner";
import { currentlySynthetic, EXPORT_PREFIX, type DataProvenance, exportFilename, isSynthetic, useProvenance } from "../../state/provenance";
import { exportUrl, getExportFormats, getFigureData, getResults, getSessionName, keepFigure, toProblem } from "./api";
import { figureDataScenes, isFigureData } from "./figureScenes";
import type { ExportFormatView, Problem, QuantityProvenance, ResultSet, ResultValue } from "./types";

const log = getLogger("screens.export");

/** PNG resolutions offered for figure export. */
export const DPI_CHOICES = [96, 192, 300, 600] as const;

/** Download file name for a figure export (SYNTHETIC- prefixed when the data is synthetic). */
export function figureFileName(formatId: string, fmt: ExportOptions["format"], sessionName = ""): string {
  const base = sessionName === "" ? formatId : `${sessionName}-${formatId}`;
  return exportFilename(`${base}.${fmt}`, currentlySynthetic());
}

/** Save a blob through a temporary link; browser only. */
export function saveBlob(blob: Blob, name: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  // Revoking at once can cancel the download in Chromium; give the browser a moment.
  setTimeout(() => { URL.revokeObjectURL(url); }, 10_000);
}

/** Fetch a figure format and render each of its figures with the shared plot exporter; returns a Problem on failure. */
export async function exportFigureFormat(
  formatId: string,
  opts: ExportOptions,
  fetchImpl: typeof fetch = fetch,
  save: (blob: Blob, name: string) => void = saveBlob,
): Promise<Problem | null> {
  const r = await getFigureData(formatId, fetchImpl);
  if (!r.ok) return toProblem(r.error);
  if (!isFigureData(r.value)) {
    log.warn("figure data has unexpected shape", { formatId });
    return { title: "Figure data cannot be drawn", detail: `format ${formatId}`, hint: "Report this export format to the lab author.", status: null };
  }
  const figures = figureDataScenes(r.value);
  if (figures.length === 0) {
    log.info("no figure data to draw yet", { formatId });
    return { title: "Nothing to plot yet", detail: `format ${formatId}`, hint: "Capture some points, then export again.", status: null };
  }
  const sessionName = await getSessionName(fetchImpl);
  const files: { blob: Blob; name: string; id: string }[] = [];
  for (const { suffix, scene } of figures) {
    const v = validateDrawable(scene);
    if (!v.ok) {
      log.warn("figure data invalid", { formatId, suffix });
      return { title: "Figure data cannot be drawn", detail: `format ${formatId} (${suffix})`, hint: "Report this export format to the lab author.", status: null };
    }
    const x = await exportFigure(scene, opts);
    if (!x.ok) {
      log.error("figure export failed", { formatId, suffix, error: x.error });
      return { title: "Figure export failed", detail: x.error, hint: "Try SVG, or a lower DPI.", status: null };
    }
    files.push({ blob: x.value.blob, name: figureFileName(`${formatId}-${suffix}`, opts.format, sessionName), id: `${formatId}-${suffix}` });
  }
  for (const f of files) {
    save(f.blob, f.name);
    const kept = await keepFigure(f.id, f.blob, fetchImpl);
    log.info("figure copy in session folder", { id: f.id, kept });
  }
  log.info("figure exported", { formatId, format: opts.format, dpi: opts.dpi, files: files.length });
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

/** Sample span text for one quantity; a dash when the server has no span. */
export function sampleSpan(p: QuantityProvenance): string {
  return p.first_sample === null || p.last_sample === null ? "-" : `${String(p.first_sample)} to ${String(p.last_sample)}`;
}

/** Per-quantity provenance table: point ids, sample span and algorithm; nothing when empty. */
export function ProvenanceTable({ provenance }: { provenance: QuantityProvenance[] }) {
  if (provenance.length === 0) return null;
  return (
    <table aria-label="Provenance" data-testid="provenance">
      <caption>Provenance</caption>
      <thead><tr><th scope="col">Quantity</th><th scope="col">Point ids</th><th scope="col">Sample span</th><th scope="col">Algorithm</th></tr></thead>
      <tbody>
        {provenance.map((p) => (
          <tr key={p.name} data-testid={`provenance-${p.name}`}>
            <th scope="row">{p.name}</th>
            <td>{p.point_ids.length === 0 ? "-" : p.point_ids.join(", ")}</td>
            <td>{sampleSpan(p)}</td>
            <td>{p.algorithm}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Report of final values with 95 % intervals, plus pending items, provenance and notes. */
export function ReportView({ results }: { results: ResultSet | null }) {
  if (results === null) return <section aria-label="Report"><p>No results yet.</p></section>;
  return (
    <section aria-label="Report">
      <h2>Report</h2>
      <SyntheticBanner provenance={results.data_provenance} />
      <p>{`Based on ${String(results.n_points)} points.`}</p>
      {results.values.length === 0 ? <p>No values computable yet.</p> : (
        <table>
          <caption>Final values</caption>
          <thead><tr><th scope="col">Quantity</th><th scope="col">Value</th><th scope="col">95 % interval</th><th scope="col">Confidence</th><th scope="col">MC check</th></tr></thead>
          <tbody>{results.values.map((v) => <ReportRow key={v.name} v={v} />)}</tbody>
        </table>
      )}
      {results.pending.length > 0 ? <p data-testid="pending">{`Pending: ${results.pending.join(", ")}`}</p> : null}
      <ProvenanceTable provenance={results.provenance} />
      {results.notes.length + results.refinement.length > 0 ? (
        <ul aria-label="Notes" data-testid="notes">
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

/** List of formats: download links first, then the DPI select and figure PNG/SVG buttons; empty list shows a message. */
export function FormatList(props: {
  formats: ExportFormatView[];
  dpi: number;
  onDpi?: (dpi: number) => void;
  onFigure?: (f: ExportFormatView, format: ExportOptions["format"]) => void;
  provenance?: DataProvenance | null;
}) {
  const { formats, dpi, onDpi, onFigure, provenance } = props;
  if (formats.length === 0) {
    return <section aria-label="Export formats"><p data-testid="no-formats">This lab declares no export formats yet.</p></section>;
  }
  // frob:ticket 01M6XAASK3B2CWRRHQZ995FN7K
  // Downloads (the primary CSV deliverable) come first so they are first in Tab order (U-08).
  const stored = useProvenance((s) => s.provenance);
  const synthetic = isSynthetic(provenance === undefined ? stored : provenance);
  const downloads = formats.filter((f) => f.download);
  const figures = formats.filter((f) => !f.download);
  return (
    <section aria-label="Export formats">
      <h2>Export</h2>
      <SyntheticBanner provenance={provenance} />
      {downloads.length > 0 ? (
        <ul aria-label="Downloads">
          {downloads.map((f) => (
            <li key={f.id} data-testid={`format-${f.id}`}>
              <a href={exportUrl(f.id)} download>{`Download ${f.title}`}</a>
              {synthetic ? <code className="synthetic-file" data-testid={`prefix-${f.id}`}>{` (saved as ${EXPORT_PREFIX}...)`}</code> : null}
            </li>
          ))}
        </ul>
      ) : null}
      {figures.length > 0 ? (
        <div role="group" aria-label="Figures">
          <label>
            {"PNG resolution "}
            <select value={dpi} onChange={(e) => { onDpi?.(Number(e.target.value)); }}>
              {DPI_CHOICES.map((d) => <option key={d} value={d}>{`${String(d)} dpi`}</option>)}
            </select>
          </label>
          <ul>
            {figures.map((f) => (
              <li key={f.id} data-testid={`format-${f.id}`}>
                <span>{f.title}</span>
                <button type="button" onClick={() => { onFigure?.(f, "png"); }}>{`Export ${f.title} as PNG`}</button>
                <button type="button" onClick={() => { onFigure?.(f, "svg"); }}>{`Export ${f.title} as SVG`}</button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

/** Results/Export screen: loads the report and format list, handles downloads and figure export. */
export function ExportScreen({ fetchImpl = fetch }: { fetchImpl?: typeof fetch }) {
  const [results, setResults] = useState<ResultSet | null>(null);
  const [formats, setFormats] = useState<ExportFormatView[]>([]);
  const [problem, setProblem] = useState<Problem | null>(null);
  const observe = useProvenance((s) => s.observe);
  const [dpi, setDpi] = useState<number>(300);

  useEffect(() => {
    const live = { current: true };
    void (async () => {
      const [r, f] = await Promise.all([getResults(fetchImpl), getExportFormats(fetchImpl)]);
      if (!live.current) return;
      if (r.ok) { setResults(r.value); observe(r.value.data_provenance); } else { log.warn("results failed", { kind: r.error.kind }); setProblem(toProblem(r.error)); }
      if (f.ok) setFormats(f.value); else { log.warn("formats failed", { kind: f.error.kind }); setProblem((p) => p ?? toProblem(f.error)); }
    })();
    return () => { live.current = false; };
  }, [fetchImpl, observe]);

  const onFigure = useCallback((f: ExportFormatView, format: ExportOptions["format"]) => {
    log.info("figure export requested", { id: f.id, format, dpi });
    void exportFigureFormat(f.id, { format, dpi }, fetchImpl).then(setProblem);
  }, [dpi, fetchImpl]);

  return (
    <section aria-label="Results and export">
      {problem ? <ProblemAlert p={problem} /> : null}
      <ReportView results={results} />
      <FormatList formats={formats} dpi={dpi} onDpi={setDpi} onFigure={onFigure} />
    </section>
  );
}
