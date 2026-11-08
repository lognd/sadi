// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
/** Calibration plot input: mirrors the API calibration payload; strings are pre-formatted by the API. */
export interface CalibrationData {
  /** Captured voltages (V). */
  volts: readonly number[];
  /** Captured heights (mm). */
  height: readonly number[];
  /** 95 % half-width of each height (mm); null/absent when no error bars are known. */
  height_u95?: readonly number[] | null;
  /** Sampled voltages of the fit line and band (two or more). */
  fit_volts: readonly number[];
  /** Fit line heights at fit_volts. */
  fit_height: readonly number[];
  /** Lower 95 % band edge at fit_volts. */
  band_lower: readonly number[];
  /** Upper 95 % band edge at fit_volts. */
  band_upper: readonly number[];
  /** Fit residuals, one per captured point (mm). */
  residuals: readonly number[];
  /** Pre-formatted 'h = (m +/- U) V + (b +/- U)' with class-rule significant figures. */
  equation: string;
  /** Pre-formatted 'r^2 = ...'. */
  r2: string;
}

/** Why a calibration payload cannot be turned into scenes. */
export type CalibrationPlotError =
  | { kind: "empty" }
  | { kind: "length_mismatch"; detail: string }
  | { kind: "non_finite"; detail: string }
  | { kind: "missing_text"; detail: string };
