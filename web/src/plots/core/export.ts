// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
import { getLogger } from "../../api/log";
import { paintScene } from "./canvas";
import type { Ctx2D } from "./canvas";
import { validateDrawable, describePlotError } from "./figure";
import type { Drawable } from "./figure";
import { sceneToSvg } from "./svg";
import { exportTheme } from "../theme";

const log = getLogger("plots.export");

/** CSS reference resolution: one scene pixel equals one pixel at 96 dpi. */
export const CSS_DPI = 96;

/** Export request: file format and target resolution (dpi applies to PNG; SVG is vector). */
export interface ExportOptions {
  readonly format: "png" | "svg";
  readonly dpi?: number;
}

/** Minimal offscreen canvas the exporter needs; injectable for tests and workers. */
export interface ExportCanvas {
  width: number;
  height: number;
  getContext(kind: "2d"): Ctx2D | null;
  toBlob(cb: (b: Blob | null) => void, type?: string): void;
}

/** Environment hooks for exportFigure. */
export interface ExportDeps {
  readonly createCanvas?: (w: number, h: number) => ExportCanvas;
}

/** Successful export payload; `text` is set for SVG. */
export interface ExportedFigure {
  readonly format: "png" | "svg";
  readonly mime: string;
  readonly width: number;
  readonly height: number;
  readonly blob: Blob;
  readonly text?: string;
}

/** Export outcome: never throws for environmental failures. */
export type ExportResult = { readonly ok: true; readonly value: ExportedFigure } | { readonly ok: false; readonly error: string };

function defaultCanvas(w: number, h: number): ExportCanvas {
  const c = document.createElement("canvas");
  c.width = w;
  c.height = h;
  return c;
}

/** Re-theme a drawable with the white, sans-font export theme, keeping its own font sizes. */
export function withExportTheme<T extends Drawable>(d: T): T {
  return { ...d, theme: { ...exportTheme, fontSize: d.theme.fontSize } };
}

/** Render the scene to PNG or SVG with the export theme, using the same layout as the on-screen canvas. */
export async function exportFigure(drawable: Drawable, opts: ExportOptions, deps: ExportDeps = {}): Promise<ExportResult> {
  const scene = withExportTheme(drawable);
  const valid = validateDrawable(scene);
  if (!valid.ok) {
    log.warn("export rejected", { error: describePlotError(valid.error) });
    return { ok: false, error: describePlotError(valid.error) };
  }
  if (opts.format === "svg") {
    const text = sceneToSvg(scene);
    log.info("svg exported", { bytes: text.length, title: scene.title });
    return { ok: true, value: { format: "svg", mime: "image/svg+xml", width: scene.width, height: scene.height, blob: new Blob([text], { type: "image/svg+xml" }), text } };
  }
  const dpi = opts.dpi ?? CSS_DPI;
  if (!(dpi > 0) || dpi > 1200) {
    log.warn("rejected dpi", { dpi });
    return { ok: false, error: `dpi out of range: ${String(dpi)}` };
  }
  const scale = dpi / CSS_DPI;
  const w = Math.round(scene.width * scale);
  const h = Math.round(scene.height * scale);
  const make = deps.createCanvas ?? (typeof document === "undefined" ? undefined : defaultCanvas);
  if (make === undefined) {
    log.error("no canvas factory available", { dpi });
    return { ok: false, error: "no canvas available" };
  }
  const canvas = make(w, h);
  const ctx = canvas.getContext("2d");
  if (ctx === null) {
    log.error("2d context unavailable", { w, h });
    return { ok: false, error: "2d context unavailable" };
  }
  paintScene(ctx, scene, scale);
  const blob = await new Promise<Blob | null>((resolve) => { canvas.toBlob(resolve, "image/png"); });
  if (blob === null) {
    log.error("png encoding failed", { w, h });
    return { ok: false, error: "png encoding failed" };
  }
  log.info("png exported", { w, h, dpi, bytes: blob.size });
  return { ok: true, value: { format: "png", mime: "image/png", width: w, height: h, blob } };
}
