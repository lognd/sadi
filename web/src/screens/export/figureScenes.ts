// frob:ticket 01M6X7JNY6ZKZKDFRM3935NES4
import { lightTheme, type Scene } from "../../plots/core";
import type { FigureData } from "./types";

/** One exportable figure: a file-name suffix and the scene to draw. */
export interface NamedScene {
  readonly suffix: string;
  readonly scene: Scene;
}

const SIZE = { width: 720, height: 460 } as const;
const MM_PER_M = 1000;

/** Wire shape check: the server sends both figures' columns, not a drawable scene. */
export function isFigureData(v: unknown): v is FigureData {
  if (typeof v !== "object" || v === null) return false;
  const o = v as Record<string, unknown>;
  return typeof o.calibration === "object" && o.calibration !== null && typeof o.stress_strain === "object" && o.stress_strain !== null;
}

/** Build the calibration and stress-strain scenes from figure data; figures with no points are skipped. */
export function figureDataScenes(d: FigureData): NamedScene[] {
  const out: NamedScene[] = [];
  const c = d.calibration;
  if (c.volts.length > 0) {
    const fit = c.fit;
    out.push({
      suffix: "calibration",
      scene: {
        ...SIZE, theme: lightTheme,
        title: "LVDT calibration, height versus voltage",
        xAxis: { label: "Voltage", unit: "V" },
        yAxis: { label: "Height", unit: "mm" },
        series: [{ id: "points", label: "captured", x: c.volts, y: c.height_m.map((h) => h * MM_PER_M), style: "points", marker: "filled" }],
        ...(fit === null || fit.band_volts.length < 2 ? {} : {
          bands: [{
            id: "band", label: "95 % band", x: fit.band_volts,
            lower: fit.band_height_m.map((h, i) => (h - (fit.band_half_width_m[i] ?? 0)) * MM_PER_M),
            upper: fit.band_height_m.map((h, i) => (h + (fit.band_half_width_m[i] ?? 0)) * MM_PER_M),
          }],
          fits: [{ id: "fit", label: "fit", x: fit.band_volts, y: fit.band_height_m.map((h) => h * MM_PER_M) }],
          annotation: { lines: [`r^2 = ${fit.r2.toFixed(4)}`, `n = ${String(fit.n)}`], anchor: "auto" as const },
        }),
      },
    });
  }
  const s = d.stress_strain;
  if (s.strain.length > 0) {
    // frob:ticket 01M72D3CTDED2MGDY721RSM8M4
    // Elastic (long) and plastic (short) rows are different specimens: one series each.
    const phaseOf = (i: number) => s.phase?.[i] ?? "";
    const pick = (excluded: boolean, phase: string) => {
      const idx = s.strain.map((_, i) => i).filter((i) => (s.excluded[i] ?? false) === excluded && phaseOf(i) === phase);
      return { x: idx.map((i) => s.strain[i] ?? 0), y: idx.map((i) => s.stress_mpa[i] ?? 0) };
    };
    const phases = [...new Set(s.strain.map((_, i) => phaseOf(i)))];
    const label = (ph: string) => (ph === "elastic" ? "elastic (long)" : ph === "plastic" ? "plastic (short)" : "included");
    const markers = ["filled", "ring"] as const;
    const series = phases.flatMap((ph, k) => {
      const kept = pick(false, ph);
      const dropped = pick(true, ph);
      return [
        ...(kept.x.length > 0 || dropped.x.length === 0
          ? [{ id: ph === "" ? "points" : `points-${ph}`, label: label(ph), style: "points" as const, marker: markers[k % markers.length] ?? "filled", ...kept }]
          : []),
        ...(dropped.x.length > 0
          ? [{ id: ph === "" ? "excluded" : `excluded-${ph}`, label: ph === "" ? "excluded" : `excluded ${ph}`, style: "points" as const, marker: "cross" as const, ...dropped }]
          : []),
      ];
    });
    out.push({
      suffix: "stress-strain",
      scene: {
        ...SIZE, theme: lightTheme,
        title: "Stress-strain",
        xAxis: { label: "Strain" },
        yAxis: { label: "Stress", unit: "MPa" },
        series,
      },
    });
  }
  return out;
}
