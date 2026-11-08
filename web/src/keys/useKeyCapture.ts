// frob:ticket 01M6W7R41EVGYTSV1B72ZQVKAB
import { useEffect, useRef } from "react";
import { getLogger } from "../api/log";
import { isTextTarget, resolveKey, type KeyAction } from "./keymap";

const log = getLogger("keys.capture");

// frob:accept COV001 because="vitest tests exist (wizard.test.tsx, keymap.test.ts) but TypeScript test discovery needs grimble, not installed here"
/** Listen on window for wizard keys and call `onAction`; text fields are left alone. */
export function useKeyCapture(onAction: (a: KeyAction) => void, nudgeActive: boolean): void {
  const handler = useRef(onAction);
  handler.current = onAction;
  useEffect(() => {
    const listener = (e: KeyboardEvent): void => {
      const target = e.target as { tagName?: string; isContentEditable?: boolean } | null;
      const action = resolveKey(e, { textFocus: isTextTarget(target), nudgeActive });
      if (action === null) return;
      e.preventDefault();
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
