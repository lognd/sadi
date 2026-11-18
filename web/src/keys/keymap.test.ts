// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
// frob:ticket 01M6WV6TC9NXXA0GCFGJNV4CSJ
import { describe, expect, it } from "vitest";
import { isControlTarget, isHeldAccept, isTextTarget, resolveKey, shouldBlurOnEscape, SHORTCUTS, TEXT_FIELD_HOTKEY_HINT, type KeyLike } from "./keymap";

const ev = (key: string, o: Partial<KeyLike> = {}): KeyLike =>
  ({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...o });
const ctx = { textFocus: false, nudgeActive: false };

describe("keymap", () => {
  it("accepts on Space and Shift+Space", () => {
    expect(resolveKey(ev(" "), ctx)).toBe("accept");
    expect(resolveKey(ev(" ", { shiftKey: true }), ctx)).toBe("accept-unsettled");
  });
  // frob:ticket 01M6WWMS5EKF26MGK5YGR0E3TZ
  it("maps F3 to export, inert in text fields", () => {
    expect(resolveKey(ev("F3"), ctx)).toBe("export");
    expect(resolveKey(ev("F3"), { ...ctx, textFocus: true })).toBeNull();
    expect(SHORTCUTS.some((s) => s.keys === "F3")).toBe(true);
  });
  it("maps Enter to the primary button", () => {
    expect(resolveKey(ev("Enter"), ctx)).toBe("primary");
  });
  // frob:ticket 01M6X9GPXGZN1KWG5S40MZ866N
  it("leaves Enter and Space to a focused control", () => {
    const c = { ...ctx, controlFocus: true };
    expect(resolveKey(ev("Enter"), c)).toBeNull();
    expect(resolveKey(ev(" "), c)).toBeNull();
    expect(resolveKey(ev(" ", { shiftKey: true }), c)).toBeNull();
    expect(resolveKey(ev("Escape"), c)).toBe("cancel");
    expect(resolveKey(ev("f"), c)).toBe("finish-phase");
  });
  it("detects button, link, summary and role targets via closest", () => {
    const sel = (m: boolean) => ({ closest: () => (m ? {} : null) });
    expect(isControlTarget(sel(true))).toBe(true);
    expect(isControlTarget(sel(false))).toBe(false);
    expect(isControlTarget(null)).toBe(false);
    expect(isControlTarget({})).toBe(false);
  });
  it("maps undo and redo keys", () => {
    expect(resolveKey(ev("z", { ctrlKey: true }), ctx)).toBe("undo");
    expect(resolveKey(ev("y", { ctrlKey: true }), ctx)).toBe("redo");
    expect(resolveKey(ev("Z", { ctrlKey: true, shiftKey: true }), ctx)).toBe("redo");
    expect(resolveKey(ev("z"), ctx)).toBe("undo");
  });
  it("arrows nudge the window when active, else change step", () => {
    expect(resolveKey(ev("ArrowLeft"), ctx)).toBe("prev-step");
    expect(resolveKey(ev("ArrowRight"), { ...ctx, nudgeActive: true })).toBe("nudge-start-later");
    expect(resolveKey(ev("ArrowLeft", { shiftKey: true }), { ...ctx, nudgeActive: true })).toBe("nudge-end-earlier");
  });
  it("is inert while a text field has focus", () => {
    expect(resolveKey(ev(" "), { ...ctx, textFocus: true })).toBeNull();
    expect(isTextTarget({ tagName: "input" })).toBe(true);
    expect(isTextTarget({ tagName: "DIV" })).toBe(false);
    expect(isTextTarget(null)).toBe(false);
  });
  it("ignores unknown keys and lists shortcuts", () => {
    expect(resolveKey(ev("q"), ctx)).toBeNull();
    expect(SHORTCUTS.length).toBeGreaterThan(5);
  });
});

// frob:ticket 01M6XAASFHD7MKMQ79XRD34EXF
describe("text-field hotkey hint (U-04)", () => {
  it("blurs only on Escape inside a text field", () => {
    expect(shouldBlurOnEscape("Escape", true)).toBe(true);
    expect(shouldBlurOnEscape("Escape", false)).toBe(false);
    expect(shouldBlurOnEscape(" ", true)).toBe(false);
  });
  it("never resolves a capture while a text field has focus", () => {
    const e = ev(" ");
    expect(resolveKey(e, { textFocus: true, nudgeActive: false, controlFocus: false })).toBeNull();
  });
  it("hint names Esc and Tab", () => {
    expect(TEXT_FIELD_HOTKEY_HINT).toMatch(/Esc.*Tab/);
  });
});

// frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
describe("held accept key", () => {
  it("ignores auto-repeat of accept keys only", () => {
    expect(isHeldAccept(true, "accept")).toBe(true);
    expect(isHeldAccept(true, "accept-unsettled")).toBe(true);
    expect(isHeldAccept(false, "accept")).toBe(false);
    expect(isHeldAccept(true, "export")).toBe(false);
  });
});
