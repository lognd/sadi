// frob:ticket 01M6W7R3TJETR6N3EVA9PMPWH8
/** TypeScript mirror of python/sadi/core/results.py; the API pre-formats display strings. */

/** State of the RSS vs Monte Carlo cross-check. */
export type McStatus = "pending" | "agrees" | "disagrees";

/** RSS vs MC flag for one result. */
export interface McCrossCheck {
  status: McStatus;
  mc_std_unc: number | null;
}

/** One reported quantity with 95 % interval and pre-formatted readouts. */
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

/** Everything the live panel shows after one recompute. */
export interface ResultSet {
  n_points: number;
  values: ResultValue[];
  pending: string[];
  notes: string[];
  refinement: string[];
  /** Real-vs-synthetic stamp; absent on older backends. */
  data_provenance?: { source: "real" | "synthetic"; synthetic: boolean; label: string; warning: string };
}

/** Result names the panel shows, in display order, with human labels. */
export const PANEL_ROWS: readonly { name: string; label: string }[] = [
  { name: "slope", label: "Calibration slope" },
  { name: "intercept", label: "Calibration intercept" },
  { name: "tare", label: "Tare" },
  { name: "E", label: "Elastic modulus E" },
  { name: "r2", label: "r^2" },
  { name: "yield_stress", label: "Yield stress" },
];
