// frob:ticket 01M6W7R3KN3HXVMJQ1D3MJNBZY
import { getLogger } from "../../api/log";
import type { FitWindow } from "./model";

const log = getLogger("plots.stressstrain.selection");

/** Fewest points an E fit accepts (backend MIN_WINDOW). */
export const MIN_WINDOW = 3;

/** Which end of the window is being moved. */
export type Edge = "first" | "last";

/** Clamp a window into [0, n-1] keeping at least MIN_WINDOW points; null when n is too small. */
export function clampWindow(w: FitWindow, n: number): FitWindow | null {
  if (n < MIN_WINDOW) {
    log.warn("too few points for a window", { n });
    return null;
  }
  const first = Math.min(Math.max(Math.round(w.first), 0), n - MIN_WINDOW);
  const last = Math.min(Math.max(Math.round(w.last), first + MIN_WINDOW - 1), n - 1);
  return { first, last };
}

/** Move one edge to an absolute index, pushing the other edge only as far as the minimum size needs. */
export function setEdge(w: FitWindow, edge: Edge, index: number, n: number): FitWindow | null {
  const target = edge === "first" ? { first: index, last: w.last } : { first: w.first, last: index };
  if (edge === "first" && index > w.last - MIN_WINDOW + 1) target.last = index + MIN_WINDOW - 1;
  if (edge === "last" && index < w.first + MIN_WINDOW - 1) target.first = index - MIN_WINDOW + 1;
  const out = clampWindow(target, n);
  if (out !== null && edge === "first" && out.first !== Math.round(index)) {
    return clampWindow({ first: out.first, last: w.last }, n);
  }
  return out;
}

/** Keyboard step: arrows move the focused edge by one (shift by five), Home/End jump to the extremes. */
export function keyStep(w: FitWindow, edge: Edge, key: string, shift: boolean, n: number): FitWindow | null {
  const step = shift ? 5 : 1;
  const cur = edge === "first" ? w.first : w.last;
  let next: number;
  switch (key) {
    case "ArrowLeft":
    case "ArrowDown":
      next = cur - step;
      break;
    case "ArrowRight":
    case "ArrowUp":
      next = cur + step;
      break;
    case "Home":
      next = 0;
      break;
    case "End":
      next = n - 1;
      break;
    default:
      return null;
  }
  const out = setEdge(w, edge, next, n);
  log.debug("key step", { key, edge, from: cur, window: out });
  return out;
}

/** Index of the point whose strain is nearest `strain` (points assumed in capture order). */
export function nearestIndex(strains: readonly number[], strain: number): number {
  let best = 0;
  let bestD = Infinity;
  strains.forEach((s, i) => {
    const d = Math.abs(s - strain);
    if (d < bestD) { bestD = d; best = i; }
  });
  return best;
}

/** Which edge a pointer at `strain` should grab: the nearer one in strain. */
export function nearestEdge(strains: readonly number[], w: FitWindow, strain: number): Edge {
  const a = Math.abs((strains[w.first] ?? 0) - strain);
  const b = Math.abs((strains[w.last] ?? 0) - strain);
  return a <= b ? "first" : "last";
}

/** Drag result: move the nearest edge to the point nearest the pointer strain. */
export function dragWindow(strains: readonly number[], w: FitWindow, strain: number, edge?: Edge): { window: FitWindow; edge: Edge } | null {
  const e = edge ?? nearestEdge(strains, w, strain);
  const out = setEdge(w, e, nearestIndex(strains, strain), strains.length);
  return out === null ? null : { window: out, edge: e };
}
