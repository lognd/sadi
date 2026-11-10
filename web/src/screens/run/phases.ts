// frob:ticket 01M6X9NXTD91A49K5KE81EQRYA
// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
/** Run-screen phases and their static wording (docs/ux.md sections 3.2 to 3.5). */

/** Phases that capture live data. */
export type RunPhase = "calibrate" | "tare" | "elastic" | "plastic";

/** Static description of one run phase. */
export interface PhaseMeta {
  /** Heading shown above the readouts. */
  readonly title: string;
  /** `phase` value sent to POST /api/session/points. */
  readonly apiPhase: string;
  /** Label of the main capture button. */
  readonly acceptLabel: string;
  /** Label of the mark-load-change button, worded for what the operator just did in this phase. */
  readonly markLabel: string;
  /** Hint under the mark button saying when to press it. */
  readonly markHint: string;
  /** Fewest accepted points before the step can be finished. */
  readonly minPoints: number;
  /** One-line instruction shown under the heading. */
  readonly instruction: string;
  /** Which plot the phase shows. */
  readonly plot: "calibration" | "stress-strain" | "none";
}

/** Wording and plot choice per phase. */
export const PHASES: Readonly<Record<RunPhase, PhaseMeta>> = {
  calibrate: {
    title: "Calibrate (LVDT)", apiPhase: "calibration", acceptLabel: "Accept point",
    markLabel: "I moved to a new gauge block", markHint: "Click this each time you move to a new gauge block; Settled cannot show until you do.", minPoints: 3,
    instruction: "Set the gauge block, click I moved to a new gauge block, wait for Settled, type the Gauge height, then press Accept point (Space).", plot: "calibration",
  },
  tare: {
    title: "Tare", apiPhase: "tare", acceptLabel: "Accept point",
    markLabel: "I emptied the hanger", markHint: "Click this once the hanger is empty and still; Settled cannot show until you do.", minPoints: 1,
    instruction: "Make sure the hanger is empty and nothing touches it, click I emptied the hanger, wait for Settled, then press Accept point (Space).", plot: "none",
  },
  elastic: {
    title: "Elastic", apiPhase: "elastic", acceptLabel: "Accept point",
    markLabel: "I added a weight", markHint: "Click this after you add a weight; Settled cannot show until you do.", minPoints: 3,
    instruction: "Add the next weight gently, click I added a weight, wait for Settled, type the Masses added, then press Accept point (Space).", plot: "stress-strain",
  },
  plastic: {
    title: "Plastic", apiPhase: "plastic", acceptLabel: "Accept point",
    markLabel: "I added a weight", markHint: "Click this after you add a weight; Settled cannot show until you do.", minPoints: 1,
    instruction: "Load past the knee in small steps: add a weight, click I added a weight, wait for Settled, then press Accept point (Space). Press F to finish the run.", plot: "stress-strain",
  },
};
