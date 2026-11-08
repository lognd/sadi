// frob:ticket 01M6WW75K1WH5X7NAKE008D0RA
// frob:accept COV001 because="covered by wsSubscribe.test.ts (vitest); TypeScript test discovery needs grimble, not installed here"
/** Subscribe adapter: feeds RESULTS_ENVELOPE frames from WS /api/stream into the results-stream client. */
import { getLogger } from "../api/log";
import { openStream, type ConnState, type StreamOptions } from "../ws/client";
import type { Subscribe } from "./useResultsStream";

const log = getLogger("results-stream.ws");

/** Options for the adapter: the shared stream options plus an optional connection-state tap. */
export interface WsSubscribeOptions extends StreamOptions {
  readonly onConn?: (s: ConnState) => void;
}

/**
 * Build a Subscribe over WS /api/stream. Each subscription owns one reconnecting socket (reused
 * openStream); only envelope frames are forwarded, trace frames and side-channel messages are
 * ignored. Replays after a reconnect are harmless: applyEnvelope drops non-newer result_versions.
 */
export function wsSubscribe(opts: WsSubscribeOptions): Subscribe {
  return (onText) => {
    const handle = openStream(opts, {
      onState: (s) => { opts.onConn?.(s); },
      onFrame: (f) => {
        if (f.type === "envelope") onText(f.body);
      },
      onMessage: () => undefined,
      onBad: (e) => { log.warn("dropping undecodable stream input", { error: e }); },
    });
    return () => { handle.close(); };
  };
}
