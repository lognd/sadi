// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import { describe, expect, it } from "vitest";
import { isTextTarget, resolveKey, SHORTCUTS, type KeyLike } from "./keymap";

const ev = (key: string, o: Partial<KeyLike> = {}): KeyLike =>
  ({ key, ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...o });
const ctx = { textFocus: false, nudgeActive: false };

describe("keymap", () => {
  it("accepts on Space and Shift+Space", () => {
    expect(resolveKey(ev(" "), ctx)).toBe("accept");
    expect(resolveKey(ev(" ", { shiftKey: true }), ctx)).toBe("accept-unsettled");
  });
  it("maps Enter to the primary button", () => {
    expect(resolveKey(ev("Enter"), ctx)).toBe("primary");
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
