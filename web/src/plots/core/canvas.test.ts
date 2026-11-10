// frob:ticket 01M72PGMY61ANRVTM7EK7B4HZG
import { describe, expect, it } from "vitest";
import { renderToCanvas } from "./canvas";
import { lightTheme } from "./index";
import type { Scene } from "./index";

/** Minimal canvas stub: a recording 2d context plus a style bag. */
function stubCanvas(): HTMLCanvasElement {
  const noop = (): void => undefined;
  const ctx = new Proxy({}, { get: () => noop, set: () => true });
  return { width: 0, height: 0, style: {}, getContext: () => ctx } as unknown as HTMLCanvasElement;
}

const x = [0, 1, 2, 3];
const scene: Scene = {
  width: 640, height: 400, title: "T", subtitle: "", footer: "",
  xAxis: { label: "x", unit: "mm" }, yAxis: { label: "y", unit: "N" },
  series: [{ id: "d", label: "d", x, y: x.map((v) => 2 * v), style: "points" }],
  theme: lightTheme,
};

describe("renderToCanvas sizing", () => {
  it("keeps the scene aspect ratio and never fixes a px height", () => {
    const c = stubCanvas();
    renderToCanvas(c, scene, { dpr: 2 });
    expect(c.style.aspectRatio).toBe("640 / 400");
    expect(c.style.height).toBe("auto");
    expect(c.style.height).not.toMatch(/px$/);
    expect(c.width).toBe(1280);
    expect(c.height).toBe(800);
  });
});
