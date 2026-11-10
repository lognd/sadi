// frob:ticket 01M6W7RB7ZFKF3DVKWW74FQXWT
// frob:ticket 01M6X9NXWB7KW3ZGQP02KDWN8N
// frob:accept COV001 because="covered by RunScreen.test.tsx (vitest); TypeScript test discovery needs grimble, not installed here"
/** Live feed for the run screens: wraps useTrace and taps the settle state and newest raw seq. */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTrace, type TraceView, type UseTraceOptions } from "../../hooks/useTrace";
import { openStream, type StreamHandle, type StreamHandlers, type StreamOptions } from "../../ws/client";
import type { CaptureWindow, ServerMessage, SettleState } from "../../ws/messages";
import { deriveLive, type LiveView } from "./live";

/** Newest facts from the text side channel. */
export interface SideState {
  readonly settle: SettleState | null;
  readonly rawSeq: number;
  readonly pointIndex: number | null;
  /** Server drift rate (V/s) of the open point, or null when unknown. */
  readonly driftVps: number | null;
  /** Capture window raw-seq span of the open point, or null before the first state. */
  readonly window: CaptureWindow | null;
  /** True when the server reports a simulated data source. */
  readonly simulated: boolean;
  /** Newest guided-run next step from a guidance message, if any has arrived. */
  readonly guidance?: GuidanceNote | null;
}

/** Guided-run advice carried by the WS guidance message. */
export interface GuidanceNote {
  readonly phase: string;
  readonly nextAction: string;
  readonly stopEarly: boolean;
  readonly stopReason: string;
}

/** Fold one message into the side state (pure; unrelated kinds return the same object); `simulated` is sticky once seen. */
// frob:ticket 2KP8YNY
export function foldSide(s: SideState, m: ServerMessage): SideState {
  if (m.kind === "hello") return { ...s, simulated: s.simulated || m.simulated };
  if (m.kind === "state") {
    return { settle: m.state, rawSeq: m.rawSeq, pointIndex: m.pointIndex ?? s.pointIndex, driftVps: m.driftVps ?? null, window: m.window ?? null, simulated: s.simulated || (m.simulated ?? false), guidance: s.guidance ?? null };
  }
  if (m.kind === "guidance") {
    return { ...s, guidance: { phase: m.phase, nextAction: m.nextAction, stopEarly: m.stopEarly, stopReason: m.stopReason } };
  }
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
  const [side, setSide] = useState<SideState>({ settle: null, rawSeq: 0, pointIndex: null, driftVps: null, window: null, simulated: false });
  const base = useRef(o.open ?? openStream);
  base.current = o.open ?? openStream;
  const open = useCallback((so: StreamOptions, h: StreamHandlers): StreamHandle =>
    base.current(so, { ...h, onMessage: (m) => { setSide((s) => foldSide(s, m)); h.onMessage(m); } }), []);
  const trace = useTrace({ ...o, open });
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => { setNowMs(Date.now()); }, 1000);
    return () => { clearInterval(id); };
  }, []);
  const atMs = trace.meta?.atMs ?? null;
  const frameAgeMs = atMs === null ? null : Math.max(0, nowMs - atMs);
  const view = useMemo(
    () => deriveLive(trace.snapshot, trace.conn, side.settle, o.simulated ?? side.simulated, side.driftVps, frameAgeMs),
    [trace.snapshot, trace.conn, side.settle, o.simulated, side.simulated, side.driftVps, frameAgeMs],
  );
  return { ...trace, view, side };
}
