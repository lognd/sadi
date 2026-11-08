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
  /** One-line instruction shown under the heading. */
  readonly instruction: string;
  /** Which plot the phase shows. */
  readonly plot: "calibration" | "stress-strain" | "none";
}

/** Wording and plot choice per phase. */
export const PHASES: Readonly<Record<RunPhase, PhaseMeta>> = {
  calibrate: {
    title: "Calibrate (LVDT)", apiPhase: "calibration", acceptLabel: "Accept point",
    instruction: "Set the gauge block, wait for Settled, then press Space.", plot: "calibration",
  },
  tare: {
    title: "Tare", apiPhase: "tare", acceptLabel: "Record tare",
    instruction: "Make sure the hanger is empty and nothing touches it, then press Space.", plot: "none",
  },
  elastic: {
    title: "Elastic", apiPhase: "elastic", acceptLabel: "Accept",
    instruction: "Add the next load gently. Press Space when Settled.", plot: "stress-strain",
  },
  plastic: {
    title: "Plastic", apiPhase: "plastic", acceptLabel: "Accept",
    instruction: "Load past the knee in small steps. Press F to finish the run.", plot: "stress-strain",
  },
};
