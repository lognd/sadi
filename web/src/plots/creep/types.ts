// frob:ticket 01M6W7R3EPVRGG4R93B7WJVKMW
/** Creep fit of one hold: strain = a + b * ln(t) with t in seconds since load (docs/lctt/creep.md). */
export interface CreepFitInput {
  /** Intercept (dimensionless strain). */
  a: number;
  /** Slope per ln(s); the number the plot reports. */
  b: number;
  /** Standard error of b, when known. */
  b_se?: number | null;
  /** Coefficient of determination. */
  r2: number;
}

/** A detected clamp slip: a strain step without a load change. */
export interface CreepSlip {
  /** Seconds since load at the step (> 0). */
  t: number;
  /** Strain at the step. */
  strain: number;
  /** Step size in mm, shown in the label. */
  size_mm: number;
}

/** One hold (one load level). */
export interface CreepHold {
  id: string;
  /** Short label, for example "20 kN". */
  label: string;
  /** Seconds since load, strictly positive, increasing. */
  t: readonly number[];
  /** Strain samples, same length as t. */
  strain: readonly number[];
  /** Fit for the hold; absent when the hold is too short to fit. */
  fit?: CreepFitInput | null;
  slips?: readonly CreepSlip[];
  /** Strain band around the settled value that counts as settled (the settle threshold). */
  settle_band?: { lower: number; upper: number } | null;
}

/** Creep plot input: one panel per hold on a shared log-time axis. */
export interface CreepData {
  holds: readonly CreepHold[];
}

/** Why a creep payload cannot be turned into a figure. */
export type CreepPlotError =
  | { kind: "empty" }
  | { kind: "length_mismatch"; detail: string }
  | { kind: "non_finite"; detail: string }
  | { kind: "non_positive_time"; detail: string };

/** Figure size options (CSS px). */
export interface CreepSizing {
  width?: number;
  /** Height per hold panel. */
  panelHeight?: number;
}
