// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
/** Reconnecting client for WS /api/stream: decodes frames, parses text, backs off on loss. */
import { err, ok, type Result } from "../api/result";
import { getLogger } from "../api/log";
import { decodeFrame, type Frame, type FrameError } from "./frame";
import { parseMessage, type MessageError, type ServerMessage } from "./messages";

const log = getLogger("ws.client");

/** Connection state shown in-plot. */
export type ConnState =
  | { readonly status: "connecting"; readonly attempt: number }
  | { readonly status: "open" }
  | { readonly status: "reconnecting"; readonly attempt: number; readonly delayMs: number }
  | { readonly status: "closed" };

/** Minimal WebSocket surface used (injectable for tests). */
export interface SocketLike {
  binaryType: string;
  onopen: ((ev: never) => unknown) | null;
  onclose: ((ev: never) => unknown) | null;
  onerror: ((ev: never) => unknown) | null;
  onmessage: ((ev: never) => unknown) | null;
  close(): void;
}

/** Timer hooks (injectable for tests). */
export interface Timers {
  setTimeout(fn: () => void, ms: number): unknown;
  clearTimeout(handle: unknown): void;
}

/** Callbacks a consumer registers. */
export interface StreamHandlers {
  onState(s: ConnState): void;
  onFrame(f: Frame): void;
  onMessage(m: ServerMessage): void;
  /** Called for undecodable input; the stream keeps running. */
  onBad(e: FrameError | MessageError | "unsupported"): void;
}

/** Client options. */
export interface StreamOptions {
  readonly url: string;
  readonly create?: (url: string) => SocketLike;
  readonly timers?: Timers;
  readonly baseDelayMs?: number;
  readonly maxDelayMs?: number;
}

/** Handle to a running stream. */
export interface StreamHandle {
  close(): void;
}

/** Exponential backoff delay for the given 1-based attempt, capped. */
export function backoffMs(attempt: number, base = 250, max = 8000): number {
  return Math.min(max, base * 2 ** Math.max(0, attempt - 1));
}

/** Route one raw socket payload to the handlers (binary -> frame, string -> message). */
export function dispatch(data: unknown, h: StreamHandlers): Result<true, FrameError | MessageError | "unsupported"> {
  if (data instanceof ArrayBuffer) {
    const f = decodeFrame(data);
    if (!f.ok) {
      log.warn("bad frame", { error: f.error });
      h.onBad(f.error);
      return f;
    }
    h.onFrame(f.value);
    return ok(true);
  }
  if (typeof data === "string") {
    const m = parseMessage(data);
    if (!m.ok) {
      log.warn("bad message", { error: m.error });
      h.onBad(m.error);
      return m;
    }
    h.onMessage(m.value);
    return ok(true);
  }
  log.warn("unsupported payload type");
  h.onBad("unsupported");
  return err("unsupported");
}

/** Open the stream and keep it open, reconnecting with capped exponential backoff until closed. */
export function openStream(opts: StreamOptions, h: StreamHandlers): StreamHandle {
  const create = opts.create ?? ((u: string): SocketLike => new WebSocket(u));
  const timers: Timers = opts.timers ?? {
    setTimeout: (fn, ms) => setTimeout(fn, ms),
    clearTimeout: (t) => { clearTimeout(t as ReturnType<typeof setTimeout>); },
  };
  let failures = 0; // consecutive lost connections; reset on open
  let sock: SocketLike | null = null;
  let timer: unknown = null;
  let closed = false;

  const connect = (): void => {
    const attempt = failures + 1;
    h.onState({ status: "connecting", attempt });
    log.info("connecting", { url: opts.url, attempt });
    const s = create(opts.url);
    sock = s;
    s.binaryType = "arraybuffer";
    s.onopen = () => {
      failures = 0;
      log.info("stream open");
      h.onState({ status: "open" });
    };
    s.onmessage = (ev: MessageEvent) => { dispatch(ev.data, h); };
    s.onerror = () => { log.warn("socket error"); };
    s.onclose = () => {
      if (closed) return;
      failures += 1;
      const delayMs = backoffMs(failures, opts.baseDelayMs, opts.maxDelayMs);
      log.warn("stream lost; will reconnect", { next_attempt: failures + 1, delayMs });
      h.onState({ status: "reconnecting", attempt: failures + 1, delayMs });
      timer = timers.setTimeout(connect, delayMs);
    };
  };
  connect();
  return {
    close: () => {
      closed = true;
      if (timer !== null) timers.clearTimeout(timer);
      sock?.close();
      log.info("stream closed by caller");
      h.onState({ status: "closed" });
    },
  };
}
