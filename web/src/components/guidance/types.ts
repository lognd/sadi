// frob:ticket 01M6W7RAPKVH796SZ6Z9EFDXQE
/** TypeScript mirror of python/sadi/labs/lctt/guidance.py (GuidanceState) as served by GET /api/results/guidance. */

/** Run phases in order. */
export type GuidancePhase = "calibrate" | "elastic" | "plastic";

/** Where the current point is: ready, still creeping, or settled and awaiting accept. */
export type HoldState = "ready" | "creeping" | "awaiting_accept";

/** Running confidence: current 95 % half-width against the target. */
export interface Confidence {
  quantity: string;
  half_width: number | null;
  target_half_width: number | null;
  relative: number | null;
  fraction: number;
  met: boolean;
}

/** Everything the guidance panel shows for one phase after one point. */
export interface GuidanceState {
  phase: GuidancePhase;
  next_action: string;
  suggested_load_kg: number | null;
  expected_value: number | null;
  unit: string;
  confidence: Confidence;
  points_taken: number;
  max_points: number;
  stop_early: boolean;
  stop_reason: string;
  proposed_next_phase: GuidancePhase | null;
  run_complete_proposed: boolean;
}
