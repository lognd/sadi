// frob:ticket 01M72TEVXXFP3PZ84SABZEDX7H
/** Load-free instruction shown whenever the server guidance carries a load; the design selector panel owns the number. */
export const GENERIC_GUIDANCE = "Add a weight to the hanger, click I added a weight, then wait for Settled.";

/** True when a guidance string names a load (kg/N/mm amounts or masses), which only the design selector may show. */
function namesLoad(next: string): boolean {
  return /\bkg\b|\bmasses\b|\d\s*(n|mm|g)\b/i.test(next);
}

/** Guidance line text: drops any load (single source is SuggestedWeightPanel) and never repeats a stop verdict. */
export function guidanceText(next: string): string {
  return namesLoad(next) ? GENERIC_GUIDANCE : next;
}
