// frob:ticket 01M72VM5X86QRPEWSW65Q9RBD8
import { useEffect, useState, type RefObject } from "react";

/** Smallest square side (CSS px) so 12+ px text still fits a readable plot. */
export const MIN_SIDE = 240;
/** Side used before the container has been measured. */
export const DEFAULT_SIDE = 360;

/** Square scene side for a measured container width (clamped, whole px). Pure. */
export function squareSide(containerWidth: number): number {
  return Number.isFinite(containerWidth) && containerWidth > 0 ? Math.max(MIN_SIDE, Math.floor(containerWidth)) : DEFAULT_SIDE;
}

/** Track a container's width with a ResizeObserver and return the square side to render the live scene at. */
export function useContainerSquare(ref: RefObject<HTMLElement | null>): number {
  const [side, setSide] = useState(DEFAULT_SIDE);
  useEffect(() => {
    const el = ref.current;
    if (el === null || typeof ResizeObserver === "undefined") return;
    setSide(squareSide(el.clientWidth));
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? el.clientWidth;
      setSide((prev) => { const n = squareSide(w); return n === prev ? prev : n; });
    });
    ro.observe(el);
    return () => { ro.disconnect(); };
  }, [ref]);
  return side;
}
