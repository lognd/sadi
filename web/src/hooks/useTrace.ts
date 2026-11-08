// frob:ticket 01M6XBY9FQS5658X6WQ5PCC2QG
// frob:ticket 01M6XAASH92DG6W6GDJBJVWSNR
// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
// frob:ticket 01M6WV6TFKP2396PW58G1WJD3B
import { stopText } from "./stopText";
import { useEffect, useMemo, useRef, useState } from "react";
import { getLogger } from "../api/log";
import { openStream, type ConnState, type StreamHandlers, type StreamHandle, type StreamOptions } from "../ws/client";
import type { ServerMessage } from "../ws/messages";
import { loadMarkTime, resultMarkTime } from "./markClock";
import { TraceWindow, type Snapshot } from "../plots/live/window";

const log = getLogger("hooks.trace");

/** Options for useTrace. */
export interface UseTraceOptions {
  /** WebSocket URL; defaults to /api/stream on the page origin. */
  readonly url?: string;
  /** Visible window in seconds (default 10). */
  readonly spanS?: number;
  /** Channel id to plot (default 0). */
  readonly channel?: number;
  /** Max display columns (default 600). */
  readonly columns?: number;
  /** Stream opener, injectable for tests. */
  readonly open?: (o: StreamOptions, h: StreamHandlers) => StreamHandle;
}

/** What useTrace returns. */
export interface TraceView {
  readonly snapshot: Snapshot;
  readonly conn: ConnState;
  /** Last server "stopped" or "analysis_failed" note, for display. */
  readonly notice: string | null;
}

/** Default stream URL for the current page, or a local fallback outside a browser. */
export function defaultStreamUrl(): string {
  if (typeof location === "undefined") return "ws://127.0.0.1:8000/api/stream";
  return `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/api/stream`;
}

/** Fold a side-channel message into window marks and the notice text; returns the new notice. */
export function applyMessage(w: TraceWindow, m: ServerMessage, lastPoint: { v: number | null }): string | null | undefined {
  switch (m.kind) {
    case "state":
      if (m.pointIndex !== null && m.pointIndex !== lastPoint.v) {
        lastPoint.v = m.pointIndex;
        w.mark({ t: loadMarkTime(w.now(), m.timeSinceLoad), kind: "load", label: `load ${String(m.pointIndex)}` });
      }
      return undefined;
    case "result":
      w.mark({
        t: resultMarkTime(w.now(), m.windowEnd), kind: m.settled ? "settled" : "forced",
        label: `${m.settled ? "settled" : "captured early"} ${m.pointIndex === null ? "" : String(m.pointIndex)}`.trim(),
      });
      return undefined;
    case "stopped":
      return stopText(m.reason, m.hint, lastPoint.v);
    case "analysis_failed":
      return `Analysis failed: ${m.reason}`;
    default:
      return undefined;
  }
}

/** Subscribe to the live stream and expose a throttled (one per animation frame) trace snapshot. */
export function useTrace(o: UseTraceOptions = {}): TraceView {
  const spanS = o.spanS ?? 10;
  const channel = o.channel ?? 0;
  const columns = o.columns ?? 600;
  const url = o.url ?? defaultStreamUrl();
  const win = useMemo(() => new TraceWindow(spanS, channel), [spanS, channel]);
  const [snapshot, setSnapshot] = useState<Snapshot>(() => win.snapshot(columns));
  const [conn, setConn] = useState<ConnState>({ status: "connecting", attempt: 1 });
  const [notice, setNotice] = useState<string | null>(null);
  const open = useRef(o.open ?? openStream);
  open.current = o.open ?? openStream;

  useEffect(() => {
    let raf: number | null = null;
    const lastPoint: { v: number | null } = { v: null };
    const schedule = (): void => {
      if (raf !== null) return;
      raf = requestAnimationFrame(() => { raf = null; setSnapshot(win.snapshot(columns)); });
    };
    log.info("subscribing", { url, spanS, channel });
    const handle = open.current({ url }, {
      onState: (s) => { setConn(s); schedule(); },
      onFrame: (f) => { if (f.type === "trace") { win.push(f); schedule(); } },
      onMessage: (m) => {
        const n = applyMessage(win, m, lastPoint);
        if (n !== undefined) setNotice(n);
        schedule();
      },
      onBad: (e) => { log.warn("dropped malformed input", { error: e }); },
    });
    return () => {
      if (raf !== null) cancelAnimationFrame(raf);
      handle.close();
      win.reset();
      log.info("unsubscribed");
    };
  }, [url, win, columns, spanS, channel]);

  return { snapshot, conn, notice };
}
