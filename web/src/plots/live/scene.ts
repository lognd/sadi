// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
/** Maps a window snapshot plus connection state to a core Scene (pure; export uses the same scene). */
import { lightTheme, type PointMarker, type Scene } from "../core";
import type { ConnState } from "../../ws/client";
import type { MarkKind, Snapshot } from "./window";

/** ADC saturation limit in volts (docs: inputs clip at +-4.9 V). */
export const SATURATION_V = 4.9;
const Y_RANGE = 5.5;
/** Peak (V) above which the fixed rail-to-rail scale with saturation limits is shown instead of auto-scaling. */
const RAIL_VIEW_V = 0.5 * SATURATION_V;
/** Smallest auto-scaled y span in volts, so a flat signal does not collapse the axis. */
const MIN_SPAN_V = 1e-3;
/** Live-trace text sizes: larger than the default theme so axis and legend stay readable when the canvas is scaled down. */
/** Smallest logical font (px) the live theme uses; the scene is rendered 1:1, so this is the CSS size. */
export const MIN_LIVE_FONT = 12;
const LIVE_THEME = { ...lightTheme, fontSize: { title: 20, subtitle: 15, label: 16, tick: 14, legend: 14, annotation: 14, footer: 12 } };

/** Y-axis bounds for a snapshot: padded signal extent, or the saturation rails once the signal is large. Pure. */
export function liveYRange(snap: Snapshot): { readonly min: number; readonly max: number; readonly rails: boolean } {
  let lo = Infinity;
  let hi = -Infinity;
  for (let i = 0; i < snap.x.length; i++) {
    const a = snap.lo[i] as number;
    const b = snap.hi[i] as number;
    if (Number.isFinite(a)) lo = Math.min(lo, a);
    if (Number.isFinite(b)) hi = Math.max(hi, b);
  }
  if (lo > hi) return { min: -Y_RANGE, max: Y_RANGE, rails: true };
  if (Math.max(Math.abs(lo), Math.abs(hi)) >= RAIL_VIEW_V) return { min: -Y_RANGE, max: Y_RANGE, rails: true };
  const mid = (lo + hi) / 2;
  const half = Math.max(hi - lo, MIN_SPAN_V) * 0.6;
  return { min: mid - half, max: mid + half, rails: false };
}

/** Sizing and labelling options. */
export interface LiveSceneOptions {
  readonly width?: number;
  readonly height?: number;
  readonly conn?: ConnState;
  readonly title?: string;
  readonly channelLabel?: string;
}

/** One-line in-plot description of the connection, or null when healthy. */
export function connLine(c: ConnState | undefined, stale: boolean): string | null {
  if (c?.status === "reconnecting") return `Reconnecting (attempt ${String(c.attempt)}, retry in ${(c.delayMs / 1000).toFixed(1)} s)`;
  if (c?.status === "connecting") return `Connecting (attempt ${String(c.attempt)})`;
  if (c?.status === "closed") return "Disconnected";
  return stale ? "Stale data" : null;
}

const KIND: Record<MarkKind, PointMarker["kind"]> = { load: "ring", settled: "filled", forced: "cross" };

function nearest(x: Float64Array, y: Float64Array, t: number): number {
  let lo = 0;
  let hi = x.length - 1;
  if (hi < 0) return 0;
  while (lo < hi) {
    const m = (lo + hi) >> 1;
    if ((x[m] as number) < t) lo = m + 1; else hi = m;
  }
  return y[lo] ?? 0;
}

/** Build the live trace scene: envelope band, mid line, event markers, auto-scaled y (saturation limits once the signal nears them). */
export function buildLiveScene(snap: Snapshot, o: LiveSceneOptions = {}): Scene {
  const ch = o.channelLabel ?? "signal";
  const line = connLine(o.conn, snap.stale);
  const markers: PointMarker[] = snap.marks.map((m, i) => ({
    id: `mark${String(i)}`, x: m.t, y: nearest(snap.x, snap.mid, m.t), kind: KIND[m.kind], label: m.label,
  }));
  const yr = liveYRange(snap);
  const lim = (id: string, label: string, v: number) => ({ id, label, x: [snap.t0, snap.t1], y: [v, v], color: "#c0392b" });
  return {
    width: o.width ?? 720,
    height: o.height ?? 360,
    title: o.title ?? "Live trace",
    subtitle: line ?? "Streaming",
    xAxis: { label: "Time", unit: "s", min: snap.t0, max: snap.t1 },
    yAxis: { label: "Voltage", unit: "V", min: yr.min, max: yr.max },
    series: [{ id: "mid", label: ch, x: snap.x, y: snap.mid, style: "line" }],
    bands: [{ id: "env", label: `${ch} min/max envelope`, x: snap.x, lower: snap.lo, upper: snap.hi }],
    fits: yr.rails ? [lim("satp", `saturation +${String(SATURATION_V)} V`, SATURATION_V), lim("satn", `saturation -${String(SATURATION_V)} V`, -SATURATION_V)] : [],
    spans: yr.rails ? [
      { id: "satpz", axis: "y", from: SATURATION_V, to: Y_RANGE, color: "#c0392b" },
      { id: "satnz", axis: "y", from: -Y_RANGE, to: -SATURATION_V, color: "#c0392b" },
    ] : [],
    markers,
    ...(line === null ? {} : { annotation: { lines: [line], anchor: "tr" as const } }),
    legend: true,
    theme: LIVE_THEME,
  };
}
