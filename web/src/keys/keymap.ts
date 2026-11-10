// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
// frob:ticket 01M6WV6TC9NXXA0GCFGJNV4CSJ
// frob:accept COV001 because="covered by keymap.test.ts (vitest); TypeScript test discovery needs grimble, not installed here"
/** Pure keyboard map for the wizard (docs/ux.md section 4); no DOM access so it is unit-testable. */

/** Every action a key can request from the wizard shell. */
export type KeyAction =
  | "accept"
  | "accept-unsettled"
  | "primary"
  | "undo"
  | "redo"
  | "nudge-start-earlier"
  | "nudge-start-later"
  | "nudge-end-earlier"
  | "nudge-end-later"
  | "prev-step"
  | "next-step"
  | "finish-phase"
  | "cancel"
  | "export"
  | "help";

/** The subset of KeyboardEvent the map needs. */
export interface KeyLike {
  key: string;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
  shiftKey: boolean;
}

/** Situation the keys are interpreted in. */
export interface KeyContext {
  /** True when a text field has focus: all keys are inert. */
  textFocus: boolean;
  /** True when a window editor is active, so arrows nudge the window instead of changing step. */
  nudgeActive: boolean;
  /** True when a button, link, summary or role=button/link has focus: Enter/Space activate it. Optional, default false. */
  controlFocus?: boolean;
}

/** One row of the on-screen shortcut list. */
export interface Shortcut {
  keys: string;
  label: string;
}

/** Shortcuts shown on screen; kept next to the map so the two cannot drift. */
export const SHORTCUTS: readonly Shortcut[] = [
  { keys: "Space", label: "Accept the current capture" },
  { keys: "Shift+Space", label: "Accept anyway (recorded as unsettled)" },
  { keys: "Enter", label: "Press the main button" },
  { keys: "Ctrl+Z", label: "Undo" },
  { keys: "Ctrl+Y", label: "Redo" },
  { keys: "Left / Right", label: "Nudge the window (or previous / next step)" },
  { keys: "[ ]  Shift+[ ]", label: "Nudge window start / end" },
  { keys: "F", label: "Finish the current phase" },
  { keys: "F3", label: "Export the current plot as PNG" },
  { keys: "Esc", label: "Cancel" },
  { keys: "?", label: "Show shortcuts" },
];

/** Map a key event to a wizard action, or null when the key means nothing here. */
export function resolveKey(e: KeyLike, ctx: KeyContext): KeyAction | null {
  if (ctx.textFocus || e.altKey) return null;
  // frob:ticket 01M6X9GPXGZN1KWG5S40MZ866N
  if (ctx.controlFocus === true && (e.key === "Enter" || e.key === " ")) return null;
  const mod = e.ctrlKey || e.metaKey;
  const k = e.key.length === 1 ? e.key.toLowerCase() : e.key;
  if (mod) {
    if (k === "z") return e.shiftKey ? "redo" : "undo";
    if (k === "y") return "redo";
    return null;
  }
  switch (e.key) {
    case " ":
      return e.shiftKey ? "accept-unsettled" : "accept";
    case "Enter":
      return "primary";
    case "Escape":
      return "cancel";
    case "F3":
      return "export";
    case "?":
      return "help";
    case "ArrowLeft":
      return ctx.nudgeActive ? (e.shiftKey ? "nudge-end-earlier" : "nudge-start-earlier") : "prev-step";
    case "ArrowRight":
      return ctx.nudgeActive ? (e.shiftKey ? "nudge-end-later" : "nudge-start-later") : "next-step";
    case "[":
      return "nudge-start-earlier";
    case "]":
      return "nudge-start-later";
    case "{":
      return "nudge-end-earlier";
    case "}":
      return "nudge-end-later";
    default:
      break;
  }
  if (k === "z") return e.shiftKey ? "redo" : "undo";
  if (k === "f") return "finish-phase";
  return null;
}

/** True when the event target is somewhere typing happens (input, textarea, select, contenteditable). */
export function isTextTarget(t: { tagName?: string; isContentEditable?: boolean } | null): boolean {
  if (t === null) return false;
  const tag = (t.tagName ?? "").toUpperCase();
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || t.isContentEditable === true;
}

/** Shared hint: why hotkeys seem dead in a field and how to get them back (U-04). */
// frob:ticket 01M6XAASFHD7MKMQ79XRD34EXF
export const TEXT_FIELD_HOTKEY_HINT = "Hotkeys pause while a text field has focus. Press Esc or Tab to leave the field and use them again.";

/** True when Escape pressed in a text field should blur it so hotkeys resume (never triggers a capture). */
// frob:ticket 01M6XAASFHD7MKMQ79XRD34EXF
export function shouldBlurOnEscape(key: string, textFocus: boolean): boolean {
  return textFocus && key === "Escape";
}

/** True when the target is (inside) a button, link, summary or role=button/link, which Enter/Space must activate. */
// frob:ticket 01M6X9GPXGZN1KWG5S40MZ866N
export function isControlTarget(t: { closest?: (sel: string) => unknown } | null): boolean {
  if (t === null || typeof t.closest !== "function") return false;
  return t.closest('button, a[href], summary, [role="button"], [role="link"]') !== null;
}

// frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
/** True when a held (auto-repeating) key would re-fire an accept action and must be ignored. */
export function isHeldAccept(repeat: boolean, action: KeyAction): boolean {
  return repeat && (action === "accept" || action === "accept-unsettled");
}
