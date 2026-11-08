// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
/** Binary frame decoder mirroring python/sadi/server/framing.py byte for byte (docs/server/websocket.md). */
import { err, ok, type Result } from "../api/result";
import { getLogger } from "../api/log";

const log = getLogger("ws.frame");

/** Frame header size in bytes. */
export const HEADER_BYTES = 24;
/** Fixed part of a TRACE payload (raw_seq .. n_points) in bytes. */
export const TRACE_HEAD_BYTES = 38;
/** Most points per channel the server sends (min/max decimation bucket cap). */
export const MAX_POINTS = 256;
const MAGIC = [0x53, 0x41, 0x44, 0x49]; // "SADI"
const VERSION = 1;
const FLAG_STALE = 1;

/** Why a binary frame could not be decoded (mirrors FrameError on the server). */
export type FrameError = "short" | "magic" | "version" | "type";

/** One channel of a trace frame: equal-length min and max arrays (min == max when undecimated). */
export interface ChannelData {
  readonly min: Float32Array;
  readonly max: Float32Array;
}

/** Header fields shared by every frame. */
export interface FrameHeader {
  readonly seq: number;
  readonly t0S: number;
  readonly stale: boolean;
}

/** A decoded TRACE frame. */
export interface TraceFrame extends FrameHeader {
  readonly type: "trace";
  readonly rawSeq: number;
  readonly durableSeq: number;
  readonly enqueuedSeq: number;
  readonly dtS: number;
  readonly nPoints: number;
  readonly channels: ReadonlyMap<number, ChannelData>;
}

/** A decoded RESULTS_ENVELOPE frame; `body` is the UTF-8 JSON text. */
export interface EnvelopeFrame extends FrameHeader {
  readonly type: "envelope";
  readonly body: string;
}

/** Any decoded binary frame. */
export type Frame = TraceFrame | EnvelopeFrame;

/** Decode one binary WebSocket message; never throws on malformed input. */
export function decodeFrame(buf: ArrayBuffer): Result<Frame, FrameError> {
  if (buf.byteLength < HEADER_BYTES) return err("short");
  const dv = new DataView(buf);
  for (let i = 0; i < MAGIC.length; i++) {
    if (dv.getUint8(i) !== MAGIC[i]) return err("magic");
  }
  if (dv.getUint8(4) !== VERSION) return err("version");
  const ftype = dv.getUint8(5);
  const header: FrameHeader = {
    stale: (dv.getUint16(6, true) & FLAG_STALE) !== 0,
    seq: Number(dv.getBigUint64(8, true)),
    t0S: dv.getFloat64(16, true),
  };
  if (ftype === 2) {
    const body = new TextDecoder().decode(new Uint8Array(buf, HEADER_BYTES));
    return ok({ type: "envelope", ...header, body });
  }
  if (ftype !== 1) return err("type");
  if (buf.byteLength < HEADER_BYTES + TRACE_HEAD_BYTES) return err("short");
  let off = HEADER_BYTES;
  const rawSeq = Number(dv.getBigUint64(off, true));
  const durableSeq = Number(dv.getBigUint64(off + 8, true));
  const enqueuedSeq = Number(dv.getBigUint64(off + 16, true));
  const dtS = dv.getFloat64(off + 24, true);
  const nCh = dv.getUint16(off + 32, true);
  const nPoints = dv.getUint32(off + 34, true);
  off += TRACE_HEAD_BYTES;
  const stride = 2 + 8 * nPoints;
  if (buf.byteLength !== off + nCh * stride) {
    log.warn("trace frame size mismatch", { bytes: buf.byteLength, nCh, nPoints });
    return err("short");
  }
  const channels = new Map<number, ChannelData>();
  for (let c = 0; c < nCh; c++) {
    const id = dv.getUint16(off, true);
    const min = new Float32Array(nPoints);
    const max = new Float32Array(nPoints);
    let p = off + 2;
    for (let i = 0; i < nPoints; i++, p += 8) {
      min[i] = dv.getFloat32(p, true);
      max[i] = dv.getFloat32(p + 4, true);
    }
    channels.set(id, { min, max });
    off += stride;
  }
  return ok({ type: "trace", ...header, rawSeq, durableSeq, enqueuedSeq, dtS, nPoints, channels });
}
