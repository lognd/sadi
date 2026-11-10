// frob:ticket 01M6WW4VK0V8K8W70AQ20AFPZP
// frob:ticket 01M6WVTVH19EXW341V5K8SM7Z4
// frob:ticket 01M6W7RATGKGPEYSMC5H8WGMBV
/** TypeScript mirror of the export and results wire shapes (python/sadi/server/routes/export.py, core/results.py). */

import type { components } from "../../api/schema";

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

/** Where one reported quantity came from (generated from the backend OpenAPI schema). */
export type QuantityProvenance = components["schemas"]["QuantityProvenance"];

/** Full report served by GET /api/results. */
export interface ResultSet {
  n_points: number;
  values: ResultValue[];
  pending: string[];
  notes: string[];
  refinement: string[];
  provenance: QuantityProvenance[];
  /** Real-vs-synthetic stamp; absent on older backends. */
  data_provenance?: components["schemas"]["DataProvenance"];
}

/** Parsed problem+json body; `hint` says what to do next. */
export interface Problem {
  title: string;
  detail: string;
  hint: string;
  status: number | null;
}

/** Calibration fit line and 95 % band as served in lctt-figure-json (heights in m). */
export interface FigureCalibrationFit {
  slope_m_per_v: number;
  intercept_m: number;
  r2: number;
  n: number;
  band_volts: number[];
  band_height_m: number[];
  band_half_width_m: number[];
}

/** Wire shape of GET /api/export/lctt-figure-json (python/sadi/labs/lctt/figure_data.py). */
export interface FigureData {
  calibration: { volts: number[]; height_m: number[]; fit: FigureCalibrationFit | null };
  stress_strain: { point_ids: string[]; strain: number[]; stress_mpa: number[]; excluded: boolean[]; phase?: string[] };
}
