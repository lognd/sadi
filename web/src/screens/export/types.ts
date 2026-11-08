// frob:ticket 01M6W7RATGKGPEYSMC5H8WGMBV
/** TypeScript mirror of the export and results wire shapes (python/sadi/server/routes/export.py, core/results.py). */

/** One export format as listed by GET /api/export. */
export interface ExportFormatView {
  id: string;
  title: string;
  media_type: string;
  download: boolean;
}

/** RSS vs Monte Carlo cross-check state. */
export interface McCrossCheck {
  status: "pending" | "agrees" | "disagrees";
  mc_std_unc: number | null;
}

/** One reported quantity with its 95 % interval and readouts. */
export interface ResultValue {
  name: string;
  value: number;
  std_unc: number;
  u95: number;
  low95: number;
  high95: number;
  unit: string;
  dof: number | null;
  display: string;
  confidence: string;
  mc: McCrossCheck;
}

/** Full report served by GET /api/results. */
export interface ResultSet {
  n_points: number;
  values: ResultValue[];
  pending: string[];
  notes: string[];
  refinement: string[];
}

/** Parsed problem+json body; `hint` says what to do next. */
export interface Problem {
  title: string;
  detail: string;
  hint: string;
  status: number | null;
}
