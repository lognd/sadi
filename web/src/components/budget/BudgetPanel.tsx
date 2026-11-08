// frob:ticket 01M6W7R432XQSR47M3W61M215J
import katex from "katex";
import { useState } from "react";
import { getLogger } from "../../api/log";
import type { BudgetRow, ResultBudget } from "./types";

const log = getLogger("components.budget");

/** Render LaTeX to an HTML string; on failure return the escaped source (never throws). */
export function renderLatex(tex: string): string {
  try {
    return katex.renderToString(tex, { throwOnError: true, displayMode: true });
  } catch (e) {
    log.warn("latex render failed", { message: e instanceof Error ? e.message : String(e) });
    return tex.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }
}

/** Split a `.latex` derivation into one display formula per line. */
export function latexLines(latex: string): string[] {
  return latex.split("\n").map((l) => l.trim()).filter((l) => l.length > 0);
}

/** Bar width in percent of the largest absolute contribution (0 when all are zero). */
export function barWidth(row: BudgetRow, rows: readonly BudgetRow[]): number {
  const max = Math.max(0, ...rows.map((r) => Math.abs(r.contribution)));
  return max === 0 ? 0 : (100 * Math.abs(row.contribution)) / max;
}

/** Ranked bar chart plus table; the dominant input is highlighted. */
export function BudgetTable({ budget }: { budget: ResultBudget }) {
  const rows = [...budget.rows].sort((a, b) => a.rank - b.rank);
  const dominantId = budget.dominant?.id ?? null;
  return (
    <table data-testid={`budget-${budget.result}`}>
      <thead>
        <tr><th>Rank</th><th>Input</th><th>Share</th><th>Percent</th><th>u</th><th>Sensitivity</th></tr>
      </thead>
      <tbody>
        {rows.map((r) => (
          <tr key={r.id} data-testid={`row-${r.id}`} data-dominant={String(r.id === dominantId)}
              className={r.id === dominantId ? "dominant" : undefined}>
            <td>{r.rank}</td>
            <th scope="row">{r.id === dominantId ? `${r.name} (dominant)` : r.name}</th>
            <td>
              <div role="img" aria-label={`${r.name}: ${r.percent.toFixed(1)} percent`}
                   className="bar" style={{ width: `${barWidth(r, rows).toFixed(1)}%` }} />
            </td>
            <td>{`${r.percent.toFixed(1)} %`}</td>
            <td>{`${String(r.std_unc)} ${r.unit}`}</td>
            <td>{String(r.sensitivity)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Formula and derivation for one result, rendered with KaTeX from `.latex`. */
export function FormulaView({ budget }: { budget: ResultBudget }) {
  const lines = latexLines(budget.latex);
  if (lines.length === 0) log.warn("no latex for result", { result: budget.result });
  return (
    <section aria-label={`Formula for ${budget.label}`} data-testid="formula">
      {lines.map((l, i) => (
        <div key={i} className="formula-line" dangerouslySetInnerHTML={{ __html: renderLatex(l) }} />
      ))}
    </section>
  );
}

/** Budget panel: pick a result to see its ranked budget, dominant input and derivation. */
export function BudgetPanel(props: { budgets: ResultBudget[]; initial?: string }) {
  const { budgets, initial } = props;
  const [selected, setSelected] = useState<string | null>(initial ?? null);
  const current = budgets.find((b) => b.result === selected) ?? null;
  const select = (name: string): void => {
    log.info("result selected", { name });
    setSelected(name);
  };
  if (budgets.length === 0) {
    return <section aria-label="Uncertainty budget"><p>No budgets yet.</p></section>;
  }
  return (
    <section aria-label="Uncertainty budget">
      <ul>
        {budgets.map((b) => (
          <li key={b.result}>
            <button type="button" aria-pressed={b.result === selected} onClick={() => { select(b.result); }}>
              {b.label}
            </button>
            {b.dominant ? ` dominated by ${b.dominant.name} (${b.dominant.percent.toFixed(1)} %)` : ""}
          </li>
        ))}
      </ul>
      {current ? (
        <div data-testid="budget-detail">
          <BudgetTable budget={current} />
          <FormulaView budget={current} />
        </div>
      ) : (
        <p>Select a result to see its budget and formula.</p>
      )}
    </section>
  );
}
