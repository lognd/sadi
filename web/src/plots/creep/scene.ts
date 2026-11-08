// frob:ticket 01M6W7R3EPVRGG4R93B7WJVKMW
import { err, ok, type Result } from "../../api/result";
import { getLogger } from "../../api/log";
import { lightTheme, type Figure, type Panel } from "../core";
import type { CreepData, CreepHold, CreepPlotError, CreepSizing } from "./types";

const log = getLogger("plots.creep");
const FIT_SAMPLES = 24;

const finite = (xs: readonly number[]): boolean => xs.every((v) => Number.isFinite(v));

/** Check lengths, finiteness and positive times of every hold; the first problem wins. */
export function validateCreep(d: CreepData): Result<CreepData, CreepPlotError> {
  if (d.holds.length === 0 || d.holds.every((h) => h.t.length === 0)) return err({ kind: "empty" });
  for (const h of d.holds) {
    if (h.t.length !== h.strain.length) {
      return err({ kind: "length_mismatch", detail: `hold ${h.id}: t and strain differ in length` });
    }
    const extra = [...(h.slips ?? []).flatMap((s) => [s.t, s.strain, s.size_mm]), ...(h.fit ? [h.fit.a, h.fit.b, h.fit.r2] : [])];
    if (!finite(h.t) || !finite(h.strain) || !finite(extra)) {
      return err({ kind: "non_finite", detail: `hold ${h.id}: NaN or Infinity` });
    }
    if (h.t.some((v) => v <= 0) || (h.slips ?? []).some((s) => s.t <= 0)) {
      return err({ kind: "non_positive_time", detail: `hold ${h.id}: time since load must be > 0` });
    }
  }
  return ok(d);
}

/** Equation lines for a fit: strain = a + b ln(t), b with its standard error when known. */
function fitLines(h: CreepHold): string[] {
  if (!h.fit) return ["no fit (hold too short)"];
  const { a, b, b_se: se, r2 } = h.fit;
  const bs = se == null ? b.toPrecision(3) : `(${b.toPrecision(3)} +/- ${se.toPrecision(2)})`;
  return [`strain = ${a.toPrecision(3)} + ${bs} ln(t)`, `r^2 = ${r2.toFixed(4)}`];
}

/** Log-spaced sample times between lo and hi for drawing the fit curve. */
function logGrid(lo: number, hi: number): number[] {
  const l0 = Math.log(lo);
  const step = (Math.log(hi) - l0) / (FIT_SAMPLES - 1);
  return Array.from({ length: FIT_SAMPLES }, (_, i) => Math.exp(l0 + step * i));
}

function holdPanel(h: CreepHold): Panel {
  const lo = Math.min(...h.t);
  const hi = Math.max(...h.t);
  const slips = h.slips ?? [];
  const fit = h.fit ?? null;
  const fx = fit && hi > lo ? logGrid(lo, hi) : [];
  return {
    id: h.id,
    yAxis: { label: `Strain ${h.label}`, unit: "1" },
    series: [{ id: `${h.id}-strain`, label: "strain", x: h.t, y: h.strain, style: "points", marker: "filled" }],
    ...(fit && fx.length > 0
      ? { fits: [{ id: `${h.id}-fit`, label: "fit", x: fx, y: fx.map((t) => fit.a + fit.b * Math.log(t)) }] }
      : {}),
    annotation: { lines: fitLines(h), anchor: "auto" },
    markers: slips.map((s, i) => ({
      id: `${h.id}-slip${String(i)}`, x: s.t, y: s.strain, kind: "cross" as const,
      label: `slip ${s.size_mm.toPrecision(2)} mm`,
    })),
    ...(h.settle_band ? { spans: [{ id: `${h.id}-settle`, axis: "y" as const, from: h.settle_band.lower, to: h.settle_band.upper }] } : {}),
  };
}

/** Map a creep payload to a figure with one panel per hold on a shared log-time axis (pure). */
export function buildCreepScene(data: CreepData, sizing: CreepSizing = {}): Result<Figure, CreepPlotError> {
  const v = validateCreep(data);
  if (!v.ok) {
    log.warn("rejecting creep payload", { kind: v.error.kind });
    return v;
  }
  const holds = v.value.holds.filter((h) => h.t.length > 0);
  log.debug("building creep figure", { holds: holds.length });
  return ok({
    width: sizing.width ?? 640,
    height: (sizing.panelHeight ?? 220) * holds.length,
    title: "Creep, strain versus time since load",
    subtitle: "shaded band: settle threshold; x marks: detected slips",
    xAxis: { label: "Time since load", unit: "s", scale: "log" },
    panels: holds.map(holdPanel),
    theme: lightTheme,
  });
}
