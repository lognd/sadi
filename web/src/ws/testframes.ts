// frob:ticket 01M6W7RAH93KKNK1WH67KWS2S7
/** Test-only encoder for the binary frame spec (independent of the decoder under test). */

/** Encode a TRACE frame; channels map id to [min[], max[]]. */
export function encodeTrace(
  seq: number, t0: number, dt: number, channels: Record<number, [number[], number[]]>, flags = 0,
): ArrayBuffer {
  const ids = Object.keys(channels).map(Number);
  const n = ids.length === 0 ? 0 : (channels[ids[0] as number] as [number[], number[]])[0].length;
  const buf = new ArrayBuffer(62 + ids.length * (2 + 8 * n));
  const dv = new DataView(buf);
  [0x53, 0x41, 0x44, 0x49].forEach((b, i) => { dv.setUint8(i, b); });
  dv.setUint8(4, 1); dv.setUint8(5, 1); dv.setUint16(6, flags, true);
  dv.setBigUint64(8, BigInt(seq), true); dv.setFloat64(16, t0, true);
  dv.setBigUint64(24, BigInt(seq), true); dv.setBigUint64(32, BigInt(seq), true); dv.setBigUint64(40, BigInt(seq), true);
  dv.setFloat64(48, dt, true); dv.setUint16(56, ids.length, true); dv.setUint32(58, n, true);
  let off = 62;
  for (const id of ids) {
    const [mn, mx] = channels[id] as [number[], number[]];
    dv.setUint16(off, id, true);
    off += 2;
    for (let i = 0; i < n; i++, off += 8) {
      dv.setFloat32(off, mn[i] as number, true);
      dv.setFloat32(off + 4, mx[i] as number, true);
    }
  }
  return buf;
}

/** Encode a RESULTS_ENVELOPE frame with a JSON body. */
export function encodeEnvelope(seq: number, t0: number, body: string, flags = 0): ArrayBuffer {
  const bytes = new TextEncoder().encode(body);
  const out = new Uint8Array(24 + bytes.length);
  const dv = new DataView(out.buffer);
  [0x53, 0x41, 0x44, 0x49].forEach((b, i) => { dv.setUint8(i, b); });
  dv.setUint8(4, 1); dv.setUint8(5, 2); dv.setUint16(6, flags, true);
  dv.setBigUint64(8, BigInt(seq), true); dv.setFloat64(16, t0, true);
  out.set(bytes, 24);
  return out.buffer;
}
