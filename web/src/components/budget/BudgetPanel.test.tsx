// frob:ticket 01M6W7R432XQSR47M3W61M215J
import { describe, expect, it, vi } from "vitest";
import { renderToString } from "react-dom/server";
import { BudgetPanel, barWidth, latexLines, renderLatex } from "./BudgetPanel";
import { getBudgets } from "./api";
import type { BudgetRow, ResultBudget } from "./types";

const row = (id: string, rank: number, contribution: number, percent: number): BudgetRow => ({
  name: id.toUpperCase(), id, value: 1, unit: "m", std_unc: 0.01, sensitivity: 2,
  direct: contribution, cross: 0, contribution, percent, rank,
});
const ra = row("a", 2, 1, 20);
const rb = row("b", 1, 4, 80);
const rows = [ra, rb];
const budget: ResultBudget = {
  result: "E", label: "Elastic modulus E", total_variance: 5, total_std_unc: 2.2,
  dominant: rb, rows,
  latex: "y = \\frac{F L}{A}\n\\frac{\\partial y}{\\partial F} = \\frac{L}{A}",
};

describe("budget panel", () => {
  it("ranks rows and highlights the dominant input", () => {
    const html = renderToString(<BudgetPanel budgets={[budget]} initial="E" />);
    expect(html.indexOf('data-testid="row-b"')).toBeLessThan(html.indexOf('data-testid="row-a"'));
    expect(html).toContain('data-dominant="true"');
    expect(html).toContain("B (dominant)");
    expect(html).toContain("80.0 %");
  });

  it("shows formula via KaTeX once a result is selected", () => {
    const html = renderToString(<BudgetPanel budgets={[budget]} initial="E" />);
    expect(html).toContain("katex");
    expect(html).toContain("Formula for Elastic modulus E");
  });

  it("prompts to select when nothing is chosen and handles empty list", () => {
    expect(renderToString(<BudgetPanel budgets={[budget]} />)).toContain("Select a result");
    expect(renderToString(<BudgetPanel budgets={[]} />)).toContain("No budgets yet");
  });

  it("scales bars and splits latex lines", () => {
    expect(barWidth(rb, rows)).toBe(100);
    expect(barWidth(ra, rows)).toBe(25);
    expect(barWidth(row("z", 1, 0, 0), [row("z", 1, 0, 0)])).toBe(0);
    expect(latexLines("a\n\n b ")).toEqual(["a", "b"]);
  });

  it("falls back to escaped source on invalid latex", () => {
    expect(renderLatex("\\frac{<")).toContain("&lt;");
  });

  it("getBudgets returns an http error Result when the endpoint is missing", async () => {
    const f = vi.fn().mockResolvedValue(new Response("nf", { status: 404 }));
    const r = await getBudgets(f);
    expect(r.ok).toBe(false);
  });
});
