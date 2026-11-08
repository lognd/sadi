// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// frob:accept COV001 because="covered by RunScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
/** Live feed for the run screens: wraps useTrace and taps the settle state and newest raw seq. */
import { useCallback, useMemo, useRef, useState } from "react";
import { useTrace, type TraceView, type UseTraceOptions } from "../../hooks/useTrace";
import { openStream, type StreamHandle, type StreamHandlers, type StreamOptions } from "../../ws/client";
import type { ServerMessage, SettleState } from "../../ws/messages";
import { deriveLive, type LiveView } from "./live";

/** Newest facts from the text side channel. */
export interface SideState {
  readonly settle: SettleState | null;
  readonly rawSeq: number;
  readonly pointIndex: number | null;
}

/** Fold one message into the side state (pure; unrelated kinds return the same object). */
export function foldSide(s: SideState, m: ServerMessage): SideState {
  if (m.kind === "state") return { settle: m.state, rawSeq: m.rawSeq, pointIndex: m.pointIndex ?? s.pointIndex };
  if (m.kind === "result") return { ...s, rawSeq: Math.max(s.rawSeq, m.rawSeq) };
  return s;
}

/** Result of useRunLive. */
export interface RunLive extends TraceView {
  readonly view: LiveView;
  readonly side: SideState;
}

/** Subscribe once (via useTrace) and derive the LiveView; `simulated` selects the Source word. */
export function useRunLive(o: UseTraceOptions & { readonly simulated?: boolean } = {}): RunLive {
  const [side, setSide] = useState<SideState>({ settle: null, rawSeq: 0, pointIndex: null });
  const base = useRef(o.open ?? openStream);
  base.current = o.open ?? openStream;
  const open = useCallback((so: StreamOptions, h: StreamHandlers): StreamHandle =>
    base.current(so, { ...h, onMessage: (m) => { setSide((s) => foldSide(s, m)); h.onMessage(m); } }), []);
  const trace = useTrace({ ...o, open });
  const view = useMemo(
    () => deriveLive(trace.snapshot, trace.conn, side.settle, o.simulated ?? false),
    [trace.snapshot, trace.conn, side.settle, o.simulated],
  );
  return { ...trace, view, side };
}
