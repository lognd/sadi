// frob:ticket 01M6W7R3KN3HXVMJQ1D3MJNBZY
/** Data contract for the stress-strain plot, mirroring python/sadi/labs/lctt (ModulusFit, YieldResult). */

/** How a point settled; mirrors SettleSource on the backend. */
export type SettleSource = "settled_window" | "forced_early" | "fixed_dwell";

/** One captured point: strain (dimensionless) and stress (MPa) with 1-sigma uncertainties. */
export interface StressStrainPoint {
  readonly index: number;
  readonly strain: number;
  readonly stress: number;
  readonly strainU: number;
  readonly stressU: number;
  readonly settleSource: SettleSource;
  readonly saturated: boolean;
}

/** E fit over an inclusive window; `display` is the API-formatted "E = ... +/- ... GPa, r^2 = ..." text. */
export interface ModulusFitView {
  readonly first: number;
  readonly last: number;
  /** Modulus in MPa (slope of stress vs strain). */
  readonly modulusMpa: number;
  /** Intercept of the fitted line in MPa. */
  readonly interceptMpa: number;
  readonly display?: string;
  readonly eGpa: number;
  readonly eU95Gpa: number;
  readonly r2: number;
  readonly lowR2: boolean;
}

/** Offset yield; strain offset is typically 0.002. */
export interface YieldView {
  readonly stress: number;
  readonly strain: number;
  readonly offset: number;
}

/** Everything the plot needs for one render. */
export interface StressStrainData {
  readonly points: readonly StressStrainPoint[];
  readonly fit: ModulusFitView | null;
  readonly yield: YieldView | null;
  readonly title?: string;
}

/** Inclusive point-index window used for the E fit. */
export interface FitWindow {
  readonly first: number;
  readonly last: number;
}
