// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
/** Maps a window snapshot plus connection state to a core Scene (pure; export uses the same scene). */
import { lightTheme, type PointMarker, type Scene } from "../core";
import type { ConnState } from "../../ws/client";
import type { MarkKind, Snapshot } from "./window";

/** ADC saturation limit in volts (docs: inputs clip at +-4.9 V). */
export const SATURATION_V = 4.9;
const Y_RANGE = 5.5;

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

/** Build the live trace scene: envelope band, mid line, +-4.9 V limits and event markers. */
export function buildLiveScene(snap: Snapshot, o: LiveSceneOptions = {}): Scene {
  const ch = o.channelLabel ?? "signal";
  const line = connLine(o.conn, snap.stale);
  const markers: PointMarker[] = snap.marks.map((m, i) => ({
    id: `mark${String(i)}`, x: m.t, y: nearest(snap.x, snap.mid, m.t), kind: KIND[m.kind], label: m.label,
  }));
  const lim = (id: string, label: string, v: number) => ({ id, label, x: [snap.t0, snap.t1], y: [v, v], color: "#c0392b" });
  return {
    width: o.width ?? 720,
    height: o.height ?? 360,
    title: o.title ?? "Live trace",
    subtitle: line ?? "Streaming",
    xAxis: { label: "Time", unit: "s", min: snap.t0, max: snap.t1 },
    yAxis: { label: "Voltage", unit: "V", min: -Y_RANGE, max: Y_RANGE },
    series: [{ id: "mid", label: ch, x: snap.x, y: snap.mid, style: "line" }],
    bands: [{ id: "env", label: `${ch} min/max envelope`, x: snap.x, lower: snap.lo, upper: snap.hi }],
    fits: [lim("satp", `saturation +${String(SATURATION_V)} V`, SATURATION_V), lim("satn", `saturation -${String(SATURATION_V)} V`, -SATURATION_V)],
    spans: [
      { id: "satpz", axis: "y", from: SATURATION_V, to: Y_RANGE, color: "#c0392b" },
      { id: "satnz", axis: "y", from: -Y_RANGE, to: -SATURATION_V, color: "#c0392b" },
    ],
    markers,
    ...(line === null ? {} : { annotation: { lines: [line], anchor: "tr" as const } }),
    legend: true,
    theme: lightTheme,
  };
}
