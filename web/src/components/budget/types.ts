// frob:ticket 01M6W7R432XQSR47M3W61M215J
/** TypeScript mirror of python/sadi/uncertainty/budget.py (Budget.payload) plus the formula. */

/** One input's share of a result's variance. */
export interface BudgetRow {
  name: string;
  id: string;
  value: number;
  unit: string;
  std_unc: number;
  sensitivity: number;
  direct: number;
  cross: number;
  contribution: number;
  percent: number;
  rank: number;
}

/** Ranked budget for one result, with the LaTeX derivation from `Uncertain.latex`. */
export interface ResultBudget {
  result: string;
  label: string;
  total_variance: number;
  total_std_unc: number;
  dominant: BudgetRow | null;
  rows: BudgetRow[];
  latex: string;
}
