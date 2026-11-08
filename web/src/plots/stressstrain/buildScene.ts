// frob:ticket 01M6W7R3KN3HXVMJQ1D3MJNBZY
import { getLogger } from "../../api/log";
import { lightTheme } from "../core";
import type { Band, FitLine, Scene, Series } from "../core";
import type { StressStrainData } from "./model";

const log = getLogger("plots.stressstrain.scene");

/** Default figure size in CSS pixels. */
export const DEFAULT_SIZE = { width: 720, height: 460 } as const;

/** Annotation text: the API display string if present, else formatted from the fit numbers. */
export function annotationText(data: StressStrainData): string | null {
  const f = data.fit;
  if (f === null) return null;
  return f.display ?? `E = ${f.eGpa.toPrecision(3)} +/- ${f.eU95Gpa.toPrecision(2)} GPa, r^2 = ${f.r2.toFixed(4)}`;
}

/** Pure mapping from stress-strain data to a renderer Scene (no DOM, deterministic). */
export function buildStressStrainScene(
  data: StressStrainData,
  size: { width: number; height: number } = DEFAULT_SIZE,
): Scene {
  const pts = data.points;
  const series: Series[] = [];
  const maxStress = Math.max(0, ...pts.map((p) => p.stress + p.stressU));
  const top = maxStress > 0 ? maxStress * 1.05 : 1;
  const maxStrain = Math.max(0, ...pts.map((p) => p.strain + p.strainU));

  const normal = pts.filter((p) => p.settleSource !== "forced_early" && !p.saturated);
  const forced = pts.filter((p) => p.settleSource === "forced_early");
  const sat = pts.filter((p) => p.saturated);
  series.push({
    id: "points", label: "settled points", style: "points", marker: "filled",
    x: normal.map((p) => p.strain), y: normal.map((p) => p.stress),
  });
  if (forced.length > 0) {
    series.push({
      id: "forced", label: "forced early", style: "points", marker: "ring",
      x: forced.map((p) => p.strain), y: forced.map((p) => p.stress),
    });
  }
  if (sat.length > 0) {
    series.push({
      id: "saturated", label: "ADC saturated", style: "points", marker: "cross",
      x: sat.map((p) => p.strain), y: sat.map((p) => p.stress),
    });
  }
  // Uncertainty bars: one two-point line per point and axis (the core has no NaN gaps).
  for (const p of pts) {
    if (p.stressU > 0) {
      series.push({ id: `uy-${String(p.index)}`, label: "", style: "line", x: [p.strain, p.strain], y: [p.stress - p.stressU, p.stress + p.stressU], color: lightTheme.mutedText });
    }
    if (p.strainU > 0) {
      series.push({ id: `ux-${String(p.index)}`, label: "", style: "line", x: [p.strain - p.strainU, p.strain + p.strainU], y: [p.stress, p.stress], color: lightTheme.mutedText });
    }
  }
  const y = data.yield;
  if (y !== null) {
    series.push({ id: "yield", label: "0.2 % offset yield", style: "points", marker: "ring", x: [y.strain], y: [y.stress], color: "#c0392b" });
  }

  const bands: Band[] = [];
  const fits: FitLine[] = [];
  const f = data.fit;
  if (f !== null && pts[f.first] !== undefined && pts[f.last] !== undefined) {
    const x0 = (pts[f.first] as { strain: number }).strain;
    const x1 = (pts[f.last] as { strain: number }).strain;
    bands.push({ id: "window", label: "fit window", x: [x0, x1], lower: [0, 0], upper: [top, top], color: "#7f8c8d" });
    const xEnd = Math.max(x1, maxStrain * 0.6);
    fits.push({
      id: "efit", label: "E fit", color: "#2c7fb8",
      x: [0, xEnd], y: [f.interceptMpa, f.interceptMpa + f.modulusMpa * xEnd],
    });
    if (y !== null) {
      const xo = Math.max(maxStrain, y.strain);
      fits.push({
        id: "offset", label: `${(y.offset * 100).toFixed(1)} % offset`, color: "#c0392b",
        x: [y.offset, xo], y: [0, f.modulusMpa * (xo - y.offset)],
      });
    }
  } else if (f !== null) {
    log.warn("fit window outside points", { first: f.first, last: f.last, n: pts.length });
  }

  const notes: string[] = [];
  if (sat.length > 0) notes.push(`Warning: ${String(sat.length)} point(s) hit ADC saturation`);
  if (forced.length > 0) notes.push(`${String(forced.length)} forced-early point(s) marked with rings`);
  if (f?.lowR2 === true) notes.push("Warning: r^2 below threshold; adjust the window");

  const ann = annotationText(data);
  log.debug("scene built", { points: pts.length, fits: fits.length, window: f === null ? null : [f.first, f.last] });
  return {
    width: size.width, height: size.height,
    title: data.title ?? "Stress-strain",
    ...(notes.length > 0 ? { footer: notes.join("; ") } : {}),
    xAxis: { label: "Strain", unit: "mm/mm", min: 0 },
    yAxis: { label: "Stress", unit: "MPa", min: 0, max: top },
    series, bands, fits,
    ...(ann === null ? {} : { annotation: { lines: [ann], anchor: "br" as const } }),
    legend: false,
    theme: lightTheme,
  };
}
