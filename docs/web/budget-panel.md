# Budget and formula panel

Status: current

<!-- frob:waive DOC007 listed in docs/README.md table only, as with sibling docs/web pages -->

Live data pending ~J73KJ11 (props and fixtures only for now).

Parent: [web layout](../web-layout.md). Data model: [uncertainty budget](../uncertainty/budget.md)
and [@uncertain](../uncertainty/uncertain.md) (`.latex`).

- `components/budget/BudgetPanel.tsx`: lists results with their dominant input; clicking one
  shows `BudgetTable` (ranked rows, bar scaled to the largest absolute contribution, percent,
  u, sensitivity, dominant row marked) and `FormulaView` (each `.latex` line rendered with KaTeX;
  invalid LaTeX falls back to escaped source and logs a warning).
- `components/budget/types.ts` mirrors `Budget.payload()` plus `result`, `label`, `latex`.
- `components/budget/api.ts` `getBudgets()` calls `GET /api/results/budgets`. That endpoint
  does not exist yet (owned by ~J73KJ11); until then the call yields an http error Result.
- KaTeX stylesheet (`katex/dist/katex.min.css`) is not yet imported by the app shell; wiring
  it into `main.tsx` is left to the screen that mounts the panel.
