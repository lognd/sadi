// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
import { err, ok, type Result } from "../../api/result";
import { getLogger } from "../../api/log";
import { lightTheme, type Scene } from "../core";
import type { CalibrationData, CalibrationPlotError } from "./types";

const log = getLogger("plots.calibration");

/** The pair of linked figures: main fit plot and residual strip sharing one x range. */
export interface CalibrationScenes {
  readonly main: Scene;
  readonly residuals: Scene;
}

/** Figure size options (CSS px). */
export interface CalibrationSizing {
  readonly width?: number;
  readonly mainHeight?: number;
  readonly residualHeight?: number;
}

const finite = (xs: readonly number[]): boolean => xs.every((v) => Number.isFinite(v));

/** Check lengths, finiteness and text fields of a payload; the first problem wins. */
export function validateCalibration(d: CalibrationData): Result<CalibrationData, CalibrationPlotError> {
  if (d.volts.length === 0) return err({ kind: "empty" });
  const n = d.volts.length;
  const nf = d.fit_volts.length;
  if (d.height.length !== n || d.residuals.length !== n || (d.height_u95 != null && d.height_u95.length !== n)) {
    return err({ kind: "length_mismatch", detail: "point arrays differ in length" });
  }
  if (nf < 2 || d.fit_height.length !== nf || d.band_lower.length !== nf || d.band_upper.length !== nf) {
    return err({ kind: "length_mismatch", detail: "fit arrays differ in length or have fewer than 2 samples" });
  }
  const all = [d.volts, d.height, d.fit_volts, d.fit_height, d.band_lower, d.band_upper, d.residuals, d.height_u95 ?? []];
  if (!all.every(finite)) return err({ kind: "non_finite", detail: "NaN or Infinity in payload" });
  if (d.equation.trim() === "" || d.r2.trim() === "") return err({ kind: "missing_text", detail: "equation or r2 empty" });
  return ok(d);
}

/** Shared x extent (data and fit) padded 5 % so both panels line up exactly. */
function xExtent(d: CalibrationData): [number, number] {
  const xs = [...d.volts, ...d.fit_volts];
  const lo = Math.min(...xs);
  const hi = Math.max(...xs);
  const pad = (hi - lo) * 0.05 || 0.5;
  return [lo - pad, hi + pad];
}

/** Map a calibration payload to the main and residual scenes (pure, no I/O). */
export function buildCalibrationScenes(
  data: CalibrationData,
  sizing: CalibrationSizing = {},
): Result<CalibrationScenes, CalibrationPlotError> {
  const v = validateCalibration(data);
  if (!v.ok) {
    log.warn("rejecting calibration payload", { kind: v.error.kind });
    return v;
  }
  const d = v.value;
  const [x0, x1] = xExtent(d);
  const width = sizing.width ?? 640;
  const n = d.volts.length;
  log.debug("building calibration scenes", { n, errorBars: d.height_u95 != null });
  const main: Scene = {
    width,
    height: sizing.mainHeight ?? 400,
    title: "LVDT calibration, height versus voltage",
    xAxis: { label: "Voltage", unit: "V", min: x0, max: x1 },
    yAxis: { label: "Height", unit: "mm" },
    series: [{
      id: "points", label: d.height_u95 == null ? "captured" : "captured (95 % error bars)",
      x: d.volts, y: d.height, style: "points", marker: "filled",
      ...(d.height_u95 == null ? {} : { yErr: d.height_u95 }),
    }],
    bands: [{ id: "band", label: "95 % band", x: d.fit_volts, lower: d.band_lower, upper: d.band_upper }],
    fits: [{ id: "fit", label: "fit", x: d.fit_volts, y: d.fit_height }],
    annotation: { lines: [d.equation, d.r2, `n = ${String(n)}`], anchor: "auto" },
    theme: lightTheme,
  };
  const residuals: Scene = {
    width,
    height: sizing.residualHeight ?? 180,
    title: "Residuals",
    xAxis: { label: "Voltage", unit: "V", min: x0, max: x1 },
    yAxis: { label: "Residual", unit: "mm" },
    series: [{ id: "res", label: "residual", x: d.volts, y: d.residuals, style: "points", marker: "filled" }],
    fits: [{ id: "zero", label: "zero", x: [x0, x1], y: [0, 0] }],
    legend: false,
    theme: lightTheme,
  };
  return ok({ main, residuals });
}
