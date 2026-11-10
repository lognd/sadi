// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
/* eslint-disable @typescript-eslint/restrict-template-expressions -- numeric geometry in attribute and font strings */
import { getLogger } from "../../api/log";
import type { DrawOp } from "./drawlist";
import { renderPlan } from "./figure";
import type { Drawable } from "./figure";

const log = getLogger("plots.canvas");

/** The subset of CanvasRenderingContext2D the renderer uses (lets tests record calls). */
export interface Ctx2D {
  fillStyle: string | CanvasGradient | CanvasPattern;
  strokeStyle: string | CanvasGradient | CanvasPattern;
  lineWidth: number;
  globalAlpha: number;
  font: string;
  textAlign: CanvasTextAlign;
  textBaseline: CanvasTextBaseline;
  save(): void;
  restore(): void;
  scale(x: number, y: number): void;
  translate(x: number, y: number): void;
  rotate(a: number): void;
  beginPath(): void;
  closePath(): void;
  moveTo(x: number, y: number): void;
  lineTo(x: number, y: number): void;
  arc(x: number, y: number, r: number, a0: number, a1: number): void;
  rect(x: number, y: number, w: number, h: number): void;
  clip(): void;
  fill(): void;
  stroke(): void;
  fillRect(x: number, y: number, w: number, h: number): void;
  strokeRect(x: number, y: number, w: number, h: number): void;
  fillText(t: string, x: number, y: number): void;
  setLineDash(d: number[]): void;
}

/** Execute a draw list on a 2D context whose coordinate system is CSS pixels. */
export function executeDrawList(ctx: Ctx2D, ops: readonly DrawOp[], fontFamily: string): void {
  for (const o of ops) {
    switch (o.op) {
      case "rect":
        if (o.fill !== undefined) {
          ctx.fillStyle = o.fill;
          ctx.fillRect(o.x, o.y, o.w, o.h);
        }
        if (o.stroke !== undefined) {
          ctx.strokeStyle = o.stroke;
          ctx.lineWidth = o.strokeWidth ?? 1;
          ctx.strokeRect(o.x, o.y, o.w, o.h);
        }
        break;
      case "line":
        ctx.strokeStyle = o.stroke;
        ctx.lineWidth = o.strokeWidth;
        ctx.beginPath();
        ctx.moveTo(o.x1, o.y1);
        ctx.lineTo(o.x2, o.y2);
        ctx.stroke();
        break;
      case "polyline":
      case "polygon": {
        if (o.points.length < 4) break;
        ctx.beginPath();
        ctx.moveTo(o.points[0] as number, o.points[1] as number);
        for (let i = 2; i < o.points.length; i += 2) ctx.lineTo(o.points[i] as number, o.points[i + 1] as number);
        if (o.op === "polygon") {
          ctx.closePath();
          ctx.fillStyle = o.fill;
          ctx.globalAlpha = o.opacity;
          ctx.fill();
          ctx.globalAlpha = 1;
        } else {
          ctx.strokeStyle = o.stroke;
          ctx.lineWidth = o.strokeWidth;
          ctx.setLineDash(o.dashed ? [6, 4] : []);
          ctx.stroke();
          ctx.setLineDash([]);
        }
        break;
      }
      case "circle":
        ctx.beginPath();
        ctx.arc(o.cx, o.cy, o.r, 0, Math.PI * 2);
        if (o.fill !== undefined) {
          ctx.fillStyle = o.fill;
          ctx.fill();
        }
        if (o.stroke !== undefined) {
          ctx.strokeStyle = o.stroke;
          ctx.lineWidth = o.strokeWidth ?? 1;
          ctx.stroke();
        }
        break;
      case "text":
        ctx.save();
        ctx.fillStyle = o.color;
        ctx.font = `${o.bold === true ? "bold " : ""}${o.size}px ${fontFamily}`;
        ctx.textAlign = o.anchor === "middle" ? "center" : o.anchor === "end" ? "right" : "left";
        ctx.textBaseline = "alphabetic";
        ctx.translate(o.x, o.y);
        if (o.rotate !== undefined) ctx.rotate((o.rotate * Math.PI) / 180);
        ctx.fillText(o.text, 0, 0);
        ctx.restore();
        break;
      case "clipBegin":
        ctx.save();
        ctx.beginPath();
        ctx.rect(o.x, o.y, o.w, o.h);
        ctx.clip();
        break;
      case "clipEnd":
        ctx.restore();
        break;
    }
  }
}

/** Options for on-screen rendering. */
export interface RenderOptions {
  /** Device pixel ratio; defaults to window.devicePixelRatio or 1. */
  readonly dpr?: number;
}

/** Render a scene to a canvas, sizing its backing store for the device pixel ratio. */
export function renderToCanvas(canvas: HTMLCanvasElement, scene: Drawable, opts: RenderOptions = {}): void {
  const dpr = opts.dpr ?? (typeof window === "undefined" ? 1 : window.devicePixelRatio || 1);
  const ctx = canvas.getContext("2d");
  if (ctx === null) {
    log.error("2d context unavailable", { title: scene.title });
    return;
  }
  canvas.width = Math.round(scene.width * dpr);
  canvas.height = Math.round(scene.height * dpr);
  canvas.style.width = `${scene.width}px`;
  // frob:ticket 01M72PGMY61ANRVTM7EK7B4HZG
  // Ratio, not a fixed px height, so CSS width scaling never distorts.
  canvas.style.height = "auto";
  canvas.style.aspectRatio = `${scene.width} / ${scene.height}`;
  paintScene(ctx, scene, dpr);
}

/** Paint a scene onto an already sized context at the given pixel scale. */
export function paintScene(ctx: Ctx2D, scene: Drawable, scale: number): void {
  const plan = renderPlan(scene);
  const ops = plan.ops;
  ctx.save();
  ctx.scale(scale, scale);
  executeDrawList(ctx, ops, plan.fontFamily);
  ctx.restore();
  log.debug("scene painted", { scale, ops: ops.length });
}
