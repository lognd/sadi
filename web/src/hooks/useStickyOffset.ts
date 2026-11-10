// frob:ticket 01M72855X7J5P97BAN234Z81W4
// frob:accept COV001 because="covered by useStickyOffset.test.ts (vitest); TypeScript frob:tests does not resolve and grimble is not installed here"
// frob:ticket 01M729FVNSJCVAHK4XBSG9NBYC
import { getLogger } from "../api/log";

const log = getLogger("hooks.useStickyOffset");

/** CSS custom property that carries the measured sticky-stack height (styles.css falls back to 11rem). */
export const STICKY_VAR = "--top-h";

/** The slice of an element we write the custom property to. */
export interface StyleRoot { style: Pick<CSSStyleDeclaration, "setProperty" | "removeProperty"> }

/** True when the element is actually `position: sticky` right now (the narrow-viewport media rule makes it static). */
export function isActuallySticky(el: HTMLElement): boolean {
  return typeof getComputedStyle === "undefined" || typeof el.nodeType !== "number" || getComputedStyle(el).position === "sticky";
}

/** Publish `el`'s height as `--top-h` on `root` while it is sticky (else leave the stylesheet value); returns a disposer. */
export function trackStickyHeight(el: HTMLElement, root: StyleRoot = document.documentElement, isSticky: (e: HTMLElement) => boolean = isActuallySticky): () => void {
  const apply = (h: number): void => {
    if (!isSticky(el)) { root.style.removeProperty(STICKY_VAR); log.debug("sticky offset cleared; element is static"); return; }
    if (!(h > 0)) return; // unmeasured (jsdom, display:none): keep the CSS fallback
    root.style.setProperty(STICKY_VAR, `${Math.ceil(h)}px`);
    log.debug("sticky offset", { px: Math.ceil(h) });
  };
  apply(el.getBoundingClientRect().height);
  const recheck = (): void => { apply(el.getBoundingClientRect().height); };
  if (typeof window !== "undefined") window.addEventListener("resize", recheck); // media rule may flip sticky without a height change
  const unlisten = (): void => { if (typeof window !== "undefined") window.removeEventListener("resize", recheck); };
  if (typeof ResizeObserver === "undefined") return () => { unlisten(); root.style.removeProperty(STICKY_VAR); };
  const ro = new ResizeObserver((entries) => {
    for (const e of entries) apply((e.target as HTMLElement).getBoundingClientRect().height);
  });
  ro.observe(el);
  return () => { unlisten(); ro.disconnect(); root.style.removeProperty(STICKY_VAR); };
}

/** Poll (per animation frame, bounded) for `find()` to return the mounted sticky element, then track it. */
export function watchStickyTop(find: () => HTMLElement | null, root?: StyleRoot, maxFrames = 120, isSticky?: (e: HTMLElement) => boolean): () => void {
  let stop: (() => void) | null = null;
  let cancelled = false;
  const tick = (left: number): void => {
    if (cancelled) return;
    const el = find();
    if (el) { stop = trackStickyHeight(el, root, isSticky); return; }
    if (left <= 0) { log.warn("sticky element never mounted; keeping CSS fallback"); return; }
    requestAnimationFrame(() => tick(left - 1));
  };
  tick(maxFrames);
  return () => { cancelled = true; stop?.(); };
}
