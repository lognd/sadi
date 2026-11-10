// frob:ticket 01M71WYRCBRPNWFTS4PNNYWM9Z
// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
/** Short per-phase guidance: 2-4 imperative lines, one field to watch, and what comes next. */

/** Guidance for one wizard phase. */
export interface StepGuide {
  /** Imperative physical actions, 2-4 short lines. */
  readonly doThis: readonly string[];
  /** The one readout field to watch and what value or state means go. */
  readonly watch: string;
  /** What the next step is. */
  readonly next: string;
}

/** Guidance keyed by wizard phase id. */
export const STEP_GUIDE: Readonly<Record<string, StepGuide>> = {
  setup: {
    doThis: ["Tighten both clamps on the wire.", "Pull gently by hand; the wire must not slip.", "Record 3 load-and-release cycles below, then press Finish."],
    watch: "Watch LVDT: it must stay steady while you pull.",
    next: "Next: calibration.",
  },
  calibration: {
    doThis: ["Move the LVDT core to a known gauge block.", "Click I moved to a new gauge block, then wait for Settle to say Settled.", "Type the Gauge height (m), then press Accept point (Space).", "Repeat for 3 or more gauge blocks, then press Finish."],
    watch: "Watch SETTLE: press Accept point only when it says Settled.",
    next: "Next: tare.",
  },
  tare: {
    doThis: ["Tare records the zero offset left after you zero by hand; every reading is corrected by it.", "Remove all weights; hang only the empty hanger.", "Click I emptied the hanger, then wait for Settle to say Settled.", "Type the Specimen diameter (m), then press Accept point (Space)."],
    watch: "Watch DRIFT: press Accept point when it is near zero.",
    next: "Next: elastic run.",
  },
  elastic: {
    doThis: ["Hang the suggested weight shown below (the first is the smallest weight); add it gently.", "Click I added a weight, then wait for Settle to say Settled.", "Type the Added mass (kg), then press Accept point (Space).", "Repeat for at least 3 weights, then press Finish."],
    watch: "Watch SETTLE: press Accept point only when it says Settled.",
    next: "Next: plastic run.",
  },
  plastic: {
    doThis: ["Keep adding weight in larger steps.", "Click I added a weight after each.", "Press Accept point (Space) on each settled reading until the wire yields."],
    watch: "Watch SIGNAL: stop if it says SATURATED.",
    next: "Next: results.",
  },
  results: {
    doThis: ["Read the fitted values below.", "Check each has a plausible uncertainty.", "Go back a step if a value is missing."],
    watch: "Watch the notes under the table for problems.",
    next: "Next: export.",
  },
  export: {
    doThis: ["Choose a file format.", "Press Download.", "Check the file opens."],
    watch: "Watch the Save / WAL field: it must say saved.",
    next: "Last step: you are done afterwards.",
  },
};
