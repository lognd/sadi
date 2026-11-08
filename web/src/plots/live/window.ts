// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
/** Scrolling time window over decoded trace frames, with a min/max envelope and event marks. */
import { getLogger } from "../../api/log";
import { MAX_POINTS, type TraceFrame } from "../../ws/frame";

const log = getLogger("plots.live.window");

/** Kind of event drawn on the trace. */
export type MarkKind = "load" | "settled" | "forced";

/** An event at stream time `t` (seconds). */
export interface Mark {
  readonly t: number;
  readonly kind: MarkKind;
  readonly label: string;
}

/** Display-ready view of the window: columns of merged min/max over [t0, t1]. */
export interface Snapshot {
  readonly t0: number;
  readonly t1: number;
  readonly x: Float64Array;
  readonly lo: Float64Array;
  readonly hi: Float64Array;
  readonly mid: Float64Array;
  readonly marks: readonly Mark[];
  readonly stale: boolean;
  readonly droppedFrames: number;
}

/** Growable parallel arrays with O(1) amortised drop-from-front. */
class Store {
  t: number[] = [];
  lo: number[] = [];
  hi: number[] = [];
  head = 0;
  get length(): number { return this.t.length - this.head; }
  trim(before: number): void {
    while (this.head < this.t.length && (this.t[this.head] as number) < before) this.head++;
    if (this.head > 4096 && this.head > this.t.length / 2) {
      this.t = this.t.slice(this.head);
      this.lo = this.lo.slice(this.head);
      this.hi = this.hi.slice(this.head);
      this.head = 0;
    }
  }
}

/** Rolling window of one channel; push frames, snapshot for drawing. */
export class TraceWindow {
  private readonly store = new Store();
  private marks: Mark[] = [];
  private prev: { seq: number; t0: number } | null = null;
  private tEnd = 0;
  private stale = false;
  private dropped = 0;

  /** Create a window `spanS` seconds wide following channel `channel`. */
  constructor(readonly spanS: number, readonly channel: number) {}

  /** Number of buckets currently held. */
  get size(): number { return this.store.length; }

  /** Append a trace frame (ignored, with a log line, when it lacks this channel). */
  push(f: TraceFrame): void {
    const ch = f.channels.get(this.channel);
    if (ch === undefined || f.nPoints === 0) {
      log.debug("frame without channel", { seq: f.seq, channel: this.channel });
      return;
    }
    const n = f.nPoints;
    let width = f.dtS;
    if (this.prev !== null) {
      const ds = f.seq - this.prev.seq;
      if (ds > 1) { this.dropped += ds - 1; log.warn("frame gap", { missing: ds - 1 }); }
      if (ds > 0 && n >= MAX_POINTS) {
        const w = (f.t0S - this.prev.t0) / ds / n;
        if (w > 0) width = w;
      }
    }
    this.prev = { seq: f.seq, t0: f.t0S };
    const s = this.store;
    for (let i = 0; i < n; i++) {
      s.t.push(f.t0S + i * width);
      s.lo.push(ch.min[i] as number);
      s.hi.push(ch.max[i] as number);
    }
    this.tEnd = f.t0S + n * width;
    this.stale = f.stale;
    s.trim(this.tEnd - this.spanS);
    if (this.marks.length > 0 && (this.marks[0] as Mark).t < this.tEnd - this.spanS) {
      this.marks = this.marks.filter((m) => m.t >= this.tEnd - this.spanS);
    }
  }

  /** Record an event mark (kept until it scrolls out of the window). */
  mark(m: Mark): void {
    log.debug("mark", { t: m.t, kind: m.kind });
    this.marks.push(m);
  }

  /** Drop all data (new run or channel change). */
  reset(): void {
    this.store.t = []; this.store.lo = []; this.store.hi = []; this.store.head = 0;
    this.marks = []; this.prev = null; this.tEnd = 0; this.stale = false; this.dropped = 0;
    log.info("window reset", { channel: this.channel });
  }

  /** Latest stream time covered by the window. */
  get now(): number { return this.tEnd; }

  /** Merge the held buckets into at most `columns` display columns. */
  snapshot(columns: number): Snapshot {
    const s = this.store;
    const t1 = this.tEnd;
    const t0 = t1 - this.spanS;
    const n = s.length;
    const cols = Math.max(1, Math.min(columns, n));
    const x = new Float64Array(n === 0 ? 0 : cols);
    const lo = new Float64Array(x.length).fill(Infinity);
    const hi = new Float64Array(x.length).fill(-Infinity);
    for (let k = s.head; k < s.t.length; k++) {
      const c = Math.min(cols - 1, Math.floor(((k - s.head) / n) * cols));
      if ((s.lo[k] as number) < (lo[c] as number)) lo[c] = s.lo[k] as number;
      if ((s.hi[k] as number) > (hi[c] as number)) hi[c] = s.hi[k] as number;
      x[c] = s.t[k] as number;
    }
    const mid = new Float64Array(x.length);
    for (let c = 0; c < x.length; c++) mid[c] = ((lo[c] as number) + (hi[c] as number)) / 2;
    return { t0, t1, x, lo, hi, mid, marks: this.marks.filter((m) => m.t >= t0), stale: this.stale, droppedFrames: this.dropped };
  }
}
