// frob:ticket 01M72855X7J5P97BAN234Z81W4
import { afterEach, describe, expect, it, vi } from "vitest";
import { STICKY_VAR, isActuallySticky, trackStickyHeight, watchStickyTop, type StyleRoot } from "./useStickyOffset";

let cb: ResizeObserverCallback = () => undefined;
const disconnect = vi.fn();
class FakeRO {
  constructor(c: ResizeObserverCallback) { cb = c; }
  observe(): void {}
  disconnect = disconnect;
}

afterEach(() => { vi.unstubAllGlobals(); });

function fakeRoot(): StyleRoot & { vars: Map<string, string> } {
  const vars = new Map<string, string>();
  return {
    vars,
    style: {
      setProperty: (k: string, v: string | null) => { vars.set(k, String(v)); },
      removeProperty: (k: string) => { const o = vars.get(k) ?? ""; vars.delete(k); return o; },
    },
  };
}

function box(h: number): HTMLElement {
  return { getBoundingClientRect: () => ({ height: h }) } as unknown as HTMLElement;
}

describe("trackStickyHeight", () => {
  it("publishes the measured height and follows resizes", () => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    const root = fakeRoot();
    const el = box(255.2);
    const stop = trackStickyHeight(el, root);
    expect(root.vars.get(STICKY_VAR)).toBe("256px");
    (el as unknown as { getBoundingClientRect: () => { height: number } }).getBoundingClientRect = () => ({ height: 300 });
    cb([{ target: el } as unknown as ResizeObserverEntry], {} as ResizeObserver);
    expect(root.vars.get(STICKY_VAR)).toBe("300px");
    stop();
    expect(disconnect).toHaveBeenCalled();
    expect(root.vars.has(STICKY_VAR)).toBe(false);
  });
  it("keeps the CSS fallback when the element is unmeasured", () => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    const root = fakeRoot();
    trackStickyHeight(box(0), root);
    expect(root.vars.has(STICKY_VAR)).toBe(false);
  });
});

describe("watchStickyTop", () => {
  it("attaches on the frame the sticky element appears", () => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    const frames: Array<() => void> = [];
    vi.stubGlobal("requestAnimationFrame", (f: () => void) => { frames.push(f); return frames.length; });
    const root = fakeRoot();
    let el: HTMLElement | null = null;
    watchStickyTop(() => el, root);
    expect(root.vars.size).toBe(0);
    el = box(200);
    frames.shift()?.();
    expect(root.vars.get(STICKY_VAR)).toBe("200px");
  });
});

describe("static element (narrow-viewport media rule)", () => {
  it("does not publish --top-h and clears a stale value when the element is not sticky", () => {
    vi.stubGlobal("ResizeObserver", FakeRO);
    const win = new EventTarget();
    vi.stubGlobal("window", win);
    const root = fakeRoot();
    root.vars.set(STICKY_VAR, "999px");
    let sticky = false;
    const el = box(120);
    const stop = trackStickyHeight(el, root, () => sticky);
    expect(root.vars.has(STICKY_VAR)).toBe(false);
    sticky = true;
    cb([{ target: el } as unknown as ResizeObserverEntry], {} as ResizeObserver);
    expect(root.vars.get(STICKY_VAR)).toBe("120px");
    sticky = false;
    win.dispatchEvent(new Event("resize"));
    expect(root.vars.has(STICKY_VAR)).toBe(false);
    stop();
  });
});

describe("isActuallySticky", () => {
  it("reads computed position and treats unmeasurable environments as sticky", () => {
    vi.stubGlobal("getComputedStyle", () => ({ position: "static" }));
    expect(isActuallySticky({ nodeType: 1 } as unknown as HTMLElement)).toBe(false);
    vi.stubGlobal("getComputedStyle", () => ({ position: "sticky" }));
    expect(isActuallySticky({ nodeType: 1 } as unknown as HTMLElement)).toBe(true);
    expect(isActuallySticky({} as unknown as HTMLElement)).toBe(true);
  });
});
