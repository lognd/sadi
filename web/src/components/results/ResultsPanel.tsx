// frob:ticket 01M6W7R3TJETR6N3EVA9PMPWH8
import { SyntheticBanner } from "../provenance/SyntheticBanner";
import { plainNote } from "../wizard/plainText";
import { getLogger } from "../../api/log";
import { PANEL_ROWS, type ResultSet, type ResultValue } from "./types";

const log = getLogger("components.results");

/** Clipboard writer injected for testability. */
export type CopyFn = (text: string) => Promise<void>;

/** Round a number to 4 significant figures for display; exponent form when very large or small. */
export function compactNumber(n: number): string {
  if (!Number.isFinite(n)) return String(n);
  if (n === 0) return "0";
  const a = Math.abs(n);
  return a >= 1e6 || a < 1e-3 ? n.toExponential(3) : String(Number(n.toPrecision(4)));
}

/** Format one result as a copyable line with units (display string is API-formatted). */
export function copyLine(label: string, v: ResultValue): string {
  return `${label}: ${v.display} [95%: ${String(v.low95)} to ${String(v.high95)} ${v.unit}]`;
}

/** Format every present row as copyable text, one line per result. */
export function copyText(rs: ResultSet): string {
  const lines: string[] = [];
  for (const row of PANEL_ROWS) {
    const v = rs.values.find((x) => x.name === row.name);
    if (v) lines.push(copyLine(row.label, v));
  }
  return lines.join("\n");
}

/** Row for one result: display, standard uncertainty, 95 % interval, confidence, MC flag. */
export function ResultRow({ label, v }: { label: string; v: ResultValue }) {
  const disagrees = v.mc.status === "disagrees";
  if (disagrees) log.warn("RSS vs MC disagree", { name: v.name, mc: v.mc.mc_std_unc });
  return (
    <tr data-testid={`result-${v.name}`}>
      <th scope="row">{label}</th>
      <td className="display">{v.display}</td>
      <td className="std-unc">{`uncertainty \u00b1${compactNumber(v.std_unc)} ${v.unit}`}</td>
      <td className="interval">{`95 % range ${compactNumber(v.low95)} to ${compactNumber(v.high95)} ${v.unit}`}</td>
      <td className="confidence">{v.confidence}</td>
      <td className="mc" data-status={v.mc.status}>
        {disagrees ? "RSS and Monte Carlo disagree" : v.mc.status === "agrees" ? "MC agrees" : ""}
      </td>
    </tr>
  );
}

/** Always-visible live results panel; props only, no fetching. */
export function ResultsPanel(props: {
  results: ResultSet;
  settleSource?: string | null;
  copy?: CopyFn;
}) {
  const { results, settleSource, copy } = props;
  const onCopy = (): void => {
    const text = copyText(results);
    log.info("copy results", { rows: results.values.length });
    if (!copy) {
      log.warn("no clipboard function injected");
      return;
    }
    copy(text).catch((e: unknown) => { log.error("copy failed", { error: String(e) }); });
  };
  return (
    <section aria-label="Results" data-testid="results-panel">
      <SyntheticBanner provenance={results.data_provenance} />
      <h2>{`Results (${String(results.n_points)} points)`}</h2>
      <div className="table-scroll" style={{ overflowX: "auto", maxWidth: "100%" }}>
      <table>
        <tbody>
          {PANEL_ROWS.map((row) => {
            const v = results.values.find((x) => x.name === row.name);
            if (v) return <ResultRow key={row.name} label={row.label} v={v} />;
            return (
              <tr key={row.name} data-testid={`result-${row.name}`}>
                <th scope="row">{row.label}</th>
                <td colSpan={5}>{results.pending.includes(row.name) ? "pending" : "n/a"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      </div>
      {settleSource ? <p className="settle">E computed from settle value: {settleSource}</p> : null}
      {results.notes.length > 0 ? (
        <ul className="notes">{results.notes.map((n) => <li key={n}>{plainNote(n)}</li>)}</ul>
      ) : null}
      <button type="button" onClick={onCopy}>Copy values</button>
    </section>
  );
}
