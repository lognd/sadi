// frob:ticket 01M72VM5X86QRPEWSW65Q9RBD8
import { useEffect, useState, type RefObject } from "react";

/** Smallest square side (CSS px) so 12+ px text still fits a readable plot. */
export const MIN_SIDE = 240;
/** Side used before the container has been measured. */
export const DEFAULT_SIDE = 360;

/** Largest square side (CSS px) regardless of container width. */
export const MAX_SIDE = 520;
/** Fraction of the viewport height the square may occupy so Accept stays on screen. */
export const VIEWPORT_FRACTION = 0.6;

/** Square scene side: min(containerWidth, 0.6*viewportHeight, MAX_SIDE), floored to whole px, never below MIN_SIDE. Pure. */
export function squareSide(containerWidth: number, viewportHeight: number = Number.POSITIVE_INFINITY): number {
  if (!Number.isFinite(containerWidth) || containerWidth <= 0) return DEFAULT_SIDE;
  const cap = Number.isFinite(viewportHeight) && viewportHeight > 0 ? Math.min(MAX_SIDE, VIEWPORT_FRACTION * viewportHeight) : MAX_SIDE;
  return Math.max(MIN_SIDE, Math.floor(Math.min(containerWidth, cap)));
}

/** Track a container's width with a ResizeObserver and return the square side to render the live scene at. */
export function useContainerSquare(ref: RefObject<HTMLElement | null>): number {
  const [side, setSide] = useState(DEFAULT_SIDE);
  useEffect(() => {
    const el = ref.current;
    if (el === null || typeof ResizeObserver === "undefined") return;
    setSide(squareSide(el.clientWidth, window.innerHeight));
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width ?? el.clientWidth;
      setSide((prev) => { const n = squareSide(w, window.innerHeight); return n === prev ? prev : n; });
    });
    ro.observe(el);
    const onResize = (): void => { setSide((prev) => { const n = squareSide(el.clientWidth, window.innerHeight); return n === prev ? prev : n; }); };
    window.addEventListener("resize", onResize);
    return () => { ro.disconnect(); window.removeEventListener("resize", onResize); };
  }, [ref]);
  return side;
}
