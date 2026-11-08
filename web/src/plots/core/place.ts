// frob:ticket 01M6WM4ZDY9EHM2BW9312B5SEY
import { getLogger } from "../../api/log";

const log = getLogger("plots.place");

/** Axis-aligned box in CSS pixels (structurally identical to layout's Rect). */
export interface Box {
  readonly x: number;
  readonly y: number;
  readonly w: number;
  readonly h: number;
}

/** A box to place: size plus ordered top-left candidate positions (earlier wins ties). */
export interface PlaceRequest {
  readonly id: string;
  readonly w: number;
  readonly h: number;
  readonly candidates: readonly { readonly x: number; readonly y: number }[];
}

/** Fixed context for placement: allowed bounds, boxes to avoid, and data vertices (pixels) to avoid. */
export interface PlaceContext {
  readonly bounds: Box;
  readonly obstacles: readonly Box[];
  readonly points: readonly { readonly x: number; readonly y: number }[];
}

/** Chosen box for a request and the penalty it incurred (0 means fully clear). */
export interface Placement {
  readonly id: string;
  readonly box: Box;
  readonly score: number;
}

const OVERLAP_PENALTY = 1e6;
const OUTSIDE_PENALTY = 1e9;

function overlapArea(a: Box, b: Box): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? w * h : 0;
}

function score(box: Box, ctx: PlaceContext, placed: readonly Box[]): number {
  let s = 0;
  const b = ctx.bounds;
  if (box.x < b.x || box.y < b.y || box.x + box.w > b.x + b.w || box.y + box.h > b.y + b.h) s += OUTSIDE_PENALTY;
  for (const o of ctx.obstacles) if (overlapArea(box, o) > 0) s += OVERLAP_PENALTY;
  for (const o of placed) {
    const a = overlapArea(box, o);
    if (a > 0) s += OVERLAP_PENALTY + a;
  }
  for (const p of ctx.points) if (p.x >= box.x && p.x <= box.x + box.w && p.y >= box.y && p.y <= box.y + box.h) s += 1;
  return s;
}

/**
 * Greedy deterministic placement: requests are handled in order, each takes its lowest-penalty
 * candidate (first candidate wins ties) and then becomes an obstacle for the rest.
 */
export function placeBoxes(requests: readonly PlaceRequest[], ctx: PlaceContext): Placement[] {
  const placed: Box[] = [];
  const out: Placement[] = [];
  for (const r of requests) {
    let best: Placement | null = null;
    for (const c of r.candidates) {
      const box = { x: c.x, y: c.y, w: r.w, h: r.h };
      const s = score(box, ctx, placed);
      if (best === null || s < best.score) best = { id: r.id, box, score: s };
      if (s === 0) break;
    }
    const chosen = best ?? { id: r.id, box: { x: ctx.bounds.x, y: ctx.bounds.y, w: r.w, h: r.h }, score: OUTSIDE_PENALTY };
    log.debug("box placed", { id: r.id, score: chosen.score });
    placed.push(chosen.box);
    out.push(chosen);
  }
  return out;
}

/** Eight candidate positions around an anchor point (right, left, above, below, then diagonals). */
export function aroundPoint(px: number, py: number, w: number, h: number, gap = 6): { x: number; y: number }[] {
  return [
    { x: px + gap, y: py - h / 2 },
    { x: px - gap - w, y: py - h / 2 },
    { x: px - w / 2, y: py - gap - h },
    { x: px - w / 2, y: py + gap },
    { x: px + gap, y: py - gap - h },
    { x: px - gap - w, y: py - gap - h },
    { x: px + gap, y: py + gap },
    { x: px - gap - w, y: py + gap },
  ];
}
