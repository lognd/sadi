// frob:ticket 01M6XAASPRSYNWC5K5MH77E8KJ
// frob:ticket 01M71MKBSXNE43ZJF2SEJ231JH
import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { contrastRatio } from "./contrast";

const css = readFileSync(new URL("../theme.css", import.meta.url), "utf8");
const crunkToml = readFileSync(new URL("../../crunk.toml", import.meta.url), "utf8");

/** Parse `--name: #hex` tokens from one CSS block. */
function tokens(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/--([\w-]+):\s*(#[0-9a-fA-F]{6})/g)) out[m[1] ?? ""] = m[2] ?? "";
  return out;
}
const lightBlock = css.slice(css.indexOf(":root,"), css.indexOf("@media (prefers-color-scheme: dark)"));
const darkBlock = css.slice(css.indexOf(':root[data-theme="dark"] {'), css.indexOf("/* ---- Tokens: theme-independent"));
const mediaBlock = css.slice(css.indexOf("@media (prefers-color-scheme: dark)"), css.indexOf(':root[data-theme="dark"] {'));

describe("theme.css WCAG AA contrast", () => {
  test("known ratios", () => {
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
  });

  test("OS-dark block matches the manual dark block", () => {
    expect(tokens(mediaBlock)).toEqual(tokens(darkBlock));
  });

  describe.each([["light", tokens(lightBlock)], ["dark", tokens(darkBlock)]] as const)("%s theme", (_name, vars) => {
    const v = (n: string): string => vars[n] ?? "#000000";
    const text: [string, string, string][] = [
      ["body text", v("fg"), v("bg")],
      ["body text on card", v("fg"), v("surface")],
      ["muted text on page", v("muted"), v("bg")],
      ["muted text on card", v("muted"), v("surface")],
      ["muted text on inset", v("muted"), v("surface-2")],
      ["button text", v("fg"), v("btn-bg")],
      ["secondary button text on button bg", v("muted"), v("btn-bg")],
      ["primary button text", v("accent-fg"), v("accent")],
      ["accent on card", v("accent"), v("surface")],
      ["ok on soft", v("ok"), v("ok-soft")],
      ["warn on soft", v("warn"), v("warn-soft")],
      ["bad on soft", v("bad"), v("bad-soft")],
      ["fg on dominant row", v("fg"), v("accent-soft")],
    ];
    test.each(text)("%s >= 4.5:1", (_n, fg, bg) => {
      expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(4.5);
    });

    const ui: [string, string, string][] = [
      ["control border on page", v("border"), v("bg")],
      ["control border on card", v("border"), v("surface")],
      ["control border on button bg", v("border"), v("btn-bg")],
      ["focus ring on page", v("focus"), v("bg")],
      ["focus ring on card", v("focus"), v("surface")],
    ];
    test.each(ui)("%s >= 3:1", (_n, fg, bg) => {
      expect(contrastRatio(fg, bg)).toBeGreaterThanOrEqual(3);
    });
  });
});

/** Parse `name = "#hex"` lines of one `crunk.toml` table (from its header to the next header). */
function tomlPalette(header: string): Record<string, string> {
  const start = crunkToml.indexOf(`\n[${header}]`);
  const rest = crunkToml.slice(start + 1);
  const end = rest.indexOf("\n[", 1);
  const out: Record<string, string> = {};
  for (const m of rest.slice(0, end < 0 ? undefined : end).matchAll(/^([\w-]+)\s*=\s*"(#[0-9a-fA-F]{6})"/gm)) {
    out[m[1] ?? ""] = m[2] ?? "";
  }
  return out;
}

describe("crunk.toml palette mirrors theme.css", () => {
  test("light palette", () => {
    expect(tomlPalette("palette")).toEqual(tokens(lightBlock));
  });
  test("dark mode", () => {
    expect(tomlPalette("palette.modes.dark")).toEqual(tokens(darkBlock));
  });
});
