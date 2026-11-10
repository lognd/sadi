// frob:ticket 01M72855X7J5P97BAN234Z81W4
import { getLogger } from "../api/log";

const log = getLogger("hooks.useStickyOffset");

/** CSS custom property that carries the measured sticky-stack height (styles.css falls back to 11rem). */
export const STICKY_VAR = "--top-h";

/** The slice of an element we write the custom property to. */
export interface StyleRoot { style: Pick<CSSStyleDeclaration, "setProperty" | "removeProperty"> }

/** Publish `el`'s height as `--top-h` on `root` now and on every resize; returns a disposer. */
export function trackStickyHeight(el: HTMLElement, root: StyleRoot = document.documentElement): () => void {
  const apply = (h: number): void => {
    if (!(h > 0)) return; // unmeasured (jsdom, display:none): keep the CSS fallback
    root.style.setProperty(STICKY_VAR, `${Math.ceil(h)}px`);
    log.debug("sticky offset", { px: Math.ceil(h) });
  };
  apply(el.getBoundingClientRect().height);
  if (typeof ResizeObserver === "undefined") return () => undefined;
  const ro = new ResizeObserver((entries) => {
    for (const e of entries) apply((e.target as HTMLElement).getBoundingClientRect().height);
  });
  ro.observe(el);
  return () => { ro.disconnect(); root.style.removeProperty(STICKY_VAR); };
}

/** Poll (per animation frame, bounded) for `find()` to return the mounted sticky element, then track it. */
export function watchStickyTop(find: () => HTMLElement | null, root?: StyleRoot, maxFrames = 120): () => void {
  let stop: (() => void) | null = null;
  let cancelled = false;
  const tick = (left: number): void => {
    if (cancelled) return;
    const el = find();
    if (el) { stop = trackStickyHeight(el, root); return; }
    if (left <= 0) { log.warn("sticky element never mounted; keeping CSS fallback"); return; }
    requestAnimationFrame(() => tick(left - 1));
  };
  tick(maxFrames);
  return () => { cancelled = true; stop?.(); };
}
