// frob:ticket 01M72VM5TYFDN445BY0W9G68B1
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { describe, expect, it } from "vitest";
import { STEP_GUIDE } from "./stepGuide";
import { PHASE_FIELDS } from "../../screens/run/inputFields";
import { PHASES } from "../../screens/run/phases";

const LABELS = new Set(Object.values(PHASE_FIELDS).flatMap((fs) => fs.map((f) => f.label)));

/** Field labels a text names after "type the ", up to a unit, comma or period. */
function typedLabels(text: string): string[] {
  return [...text.matchAll(/[Tt]ype the ([^(,.]+?)(?: \(|,|\.|$)/g)].map((m) => (m[1] ?? "").trim());
}

describe("instruction text names real fields", () => {
  const texts = [
    ...Object.values(STEP_GUIDE).flatMap((g) => g.doThis),
    ...Object.values(PHASES).map((p) => p.instruction),
  ];
  it("finds at least one typed label", () => {
    expect(texts.flatMap(typedLabels).length).toBeGreaterThan(0);
  });
  it("every typed label exists in PHASE_FIELDS", () => {
    for (const t of texts) {
      for (const label of typedLabels(t)) expect(LABELS.has(label), `${label} in "${t}"`).toBe(true);
    }
  });
});
