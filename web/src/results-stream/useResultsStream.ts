// frob:ticket 01M6W7RB0GPGHTABW7P4XEGRNJ
// frob:accept COV001 because="covered by results-stream.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
/** React hook and transport-agnostic controller for the versioned results stream. */
import { useEffect, useState } from "react";
import { getLogger } from "../api/log";
import { parseEnvelope } from "./envelope";
import { applyEnvelope, EMPTY_STATE, type StreamState } from "./store";

const log = getLogger("results-stream.hook");

/** Source of raw envelope JSON texts; returns an unsubscribe function. */
export type Subscribe = (onText: (text: string) => void) => () => void;

/** Subscribe, parse and fold envelopes; calls onState after each change. Returns unsubscribe. */
export function connectResults(subscribe: Subscribe, onState: (s: StreamState) => void): () => void {
  let state = EMPTY_STATE;
  log.info("subscribing to results stream");
  const off = subscribe((text) => {
    const p = parseEnvelope(text);
    if (!p.ok) {
      log.warn("bad envelope", { error: p.error });
      return;
    }
    const next = applyEnvelope(state, p.value);
    if (next !== state) {
      state = next;
      onState(state);
    }
  });
  return () => {
    log.info("unsubscribing from results stream");
    off();
  };
}

/** Hook: live StreamState from the given subscribe source (must be referentially stable). */
export function useResultsStream(subscribe: Subscribe): StreamState {
  const [state, setState] = useState<StreamState>(EMPTY_STATE);
  useEffect(() => connectResults(subscribe, setState), [subscribe]);
  return state;
}
