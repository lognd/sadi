// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import { useEffect, useRef } from "react";
import { getLogger } from "../api/log";
import { isControlTarget, isHeldAccept, isTextTarget, resolveKey, shouldBlurOnEscape, type KeyAction } from "./keymap";

const log = getLogger("keys.capture");

// frob:accept COV001 because="vitest tests exist (wizard.test.tsx, keymap.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Listen on window for wizard keys and call `onAction`; text fields are left alone. */
export function useKeyCapture(onAction: (a: KeyAction) => void, nudgeActive: boolean): void {
  const handler = useRef(onAction);
  handler.current = onAction;
  useEffect(() => {
    const listener = (e: KeyboardEvent): void => {
      const target = e.target as { tagName?: string; isContentEditable?: boolean; closest?: (sel: string) => unknown } | null;
      // frob:ticket 01M6XAASFHD7MKMQ79XRD34EXF
      if (shouldBlurOnEscape(e.key, isTextTarget(target))) {
        (e.target as HTMLElement).blur();
        log.debug("escape blurred text field");
        return;
      }
      // frob:ticket 01M6X9GPXGZN1KWG5S40MZ866N
      const action = resolveKey(e, { textFocus: isTextTarget(target), nudgeActive, controlFocus: isControlTarget(target) });
      if (action === null) return;
      e.preventDefault();
      // frob:ticket 01M72D37RN0VN65DDCSPWHJMJ7
      if (isHeldAccept(e.repeat, action)) {
        log.debug("held accept key ignored", { key: e.key });
        return;
      }
      log.debug("key action", { key: e.key, action });
      handler.current(action);
    };
    window.addEventListener("keydown", listener);
    log.debug("key capture attached");
    return () => {
      window.removeEventListener("keydown", listener);
      log.debug("key capture detached");
    };
  }, [nudgeActive]);
}
