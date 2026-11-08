// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
/* eslint-disable @typescript-eslint/restrict-template-expressions -- numeric geometry in attribute and font strings */
import type { DrawOp } from "./drawlist";
import { renderPlan } from "./figure";
import type { Drawable } from "./figure";

/** Escape text for XML content and attribute values. */
function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function pts(p: readonly number[]): string {
  const out: string[] = [];
  for (let i = 0; i < p.length; i += 2) out.push(`${p[i] as number},${p[i + 1] as number}`);
  return out.join(" ");
}

/** Serialize a draw list to an SVG document string. */
export function drawListToSvg(ops: readonly DrawOp[], width: number, height: number, fontFamily: string): string {
  const parts: string[] = [];
  const defs: string[] = [];
  let clipN = 0;
  parts.push(`<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}" font-family="${esc(fontFamily)}">`);
  let open = 0;
  for (const o of ops) {
    switch (o.op) {
      case "rect":
        parts.push(`<rect x="${o.x}" y="${o.y}" width="${o.w}" height="${o.h}" fill="${o.fill ?? "none"}"${o.stroke !== undefined ? ` stroke="${o.stroke}" stroke-width="${o.strokeWidth ?? 1}"` : ""}/>`);
        break;
      case "line":
        parts.push(`<line x1="${o.x1}" y1="${o.y1}" x2="${o.x2}" y2="${o.y2}" stroke="${o.stroke}" stroke-width="${o.strokeWidth}"/>`);
        break;
      case "polyline":
        if (o.points.length >= 4) parts.push(`<polyline points="${pts(o.points)}" fill="none" stroke="${o.stroke}" stroke-width="${o.strokeWidth}"${o.dashed ? ' stroke-dasharray="6 4"' : ""}/>`);
        break;
      case "polygon":
        if (o.points.length >= 4) parts.push(`<polygon points="${pts(o.points)}" fill="${o.fill}" fill-opacity="${o.opacity}"/>`);
        break;
      case "circle":
        parts.push(`<circle cx="${o.cx}" cy="${o.cy}" r="${o.r}" fill="${o.fill ?? "none"}"${o.stroke !== undefined ? ` stroke="${o.stroke}" stroke-width="${o.strokeWidth ?? 1}"` : ""}/>`);
        break;
      case "text": {
        const anchor = o.anchor;
        const rot = o.rotate !== undefined ? ` transform="rotate(${o.rotate} ${o.x} ${o.y})"` : "";
        parts.push(`<text x="${o.x}" y="${o.y}" font-size="${o.size}" fill="${o.color}" text-anchor="${anchor}"${o.bold === true ? ' font-weight="bold"' : ""}${rot}>${esc(o.text)}</text>`);
        break;
      }
      case "clipBegin": {
        const id = `clip${clipN++}`;
        defs.push(`<clipPath id="${id}"><rect x="${o.x}" y="${o.y}" width="${o.w}" height="${o.h}"/></clipPath>`);
        parts.push(`<g clip-path="url(#${id})">`);
        open++;
        break;
      }
      case "clipEnd":
        if (open > 0) {
          parts.push("</g>");
          open--;
        }
        break;
    }
  }
  while (open-- > 0) parts.push("</g>");
  parts.splice(1, 0, ...(defs.length > 0 ? [`<defs>${defs.join("")}</defs>`] : []));
  parts.push("</svg>");
  return parts.join("\n") + "\n";
}

/** Serialize a scene to SVG using the same layout the canvas uses. */
export function sceneToSvg(scene: Drawable): string {
  const plan = renderPlan(scene);
  return drawListToSvg(plan.ops, plan.width, plan.height, plan.fontFamily);
}
