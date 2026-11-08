// frob:ticket 01M6XAASPRSYNWC5K5MH77E8KJ
import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { contrastRatio } from "./contrast";

const css = readFileSync(new URL("../styles.css", import.meta.url), "utf8");
const vars: Record<string, string> = {};
for (const m of css.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) vars[m[1] ?? ""] = m[2] ?? "";
const v = (n: string): string => vars[n] ?? "#000000";
const BUTTON_BG = /background:\s*(#[0-9a-fA-F]{6});/.exec(css.slice(css.indexOf(".btn, button")))?.[1] ?? "#000000";

describe("styles.css WCAG AA contrast", () => {
  test("known ratios", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
  });

  const text: [string, string, string][] = [
    ["body text", v("fg"), v("bg")],
    ["muted text", v("muted"), v("bg")],
    ["button text", v("fg"), BUTTON_BG],
    ["secondary button text on page", v("muted"), v("bg")],
    ["secondary button text on button bg", v("muted"), BUTTON_BG],
    ["primary button text", v("accent-fg"), v("accent")],
  ];
  test.each(text)("%s >= 4.5:1", (_n, fg, bg) => {
    expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5);
  });

  const ui: [string, string, string][] = [
    ["control border on page", v("border"), v("bg")],
    ["control border on button bg", v("border"), BUTTON_BG],
    ["focus ring on page", v("focus"), v("bg")],
    // outline-offset: 2px keeps the ring on the page background, not on the button.
  ];
  test.each(ui)("%s >= 3:1", (_n, fg, bg) => {
    expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(3);
  });
});
