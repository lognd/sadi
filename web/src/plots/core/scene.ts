// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
import type { Theme } from "../theme";

/** Numeric column; typed arrays are preferred for large series. */
export type Column = ArrayLike<number>;

/** Axis description: label text and unit are rendered as "label (unit)". */
export interface AxisSpec {
  readonly label: string;
  readonly unit?: string;
  /** Fixed lower bound; omit to derive from the data. */
  readonly min?: number;
  /** Fixed upper bound; omit to derive from the data. */
  readonly max?: number;
}

/** Marker glyph for point series (live-view.md 7.2: captured filled, live ringed, rejected cross). */
export type MarkerKind = "filled" | "ring" | "cross";

/** A data series drawn as a polyline or as markers. */
export interface Series {
  readonly id: string;
  readonly label: string;
  readonly x: Column;
  readonly y: Column;
  readonly style: "line" | "points";
  readonly marker?: MarkerKind;
  readonly color?: string;
  readonly dashed?: boolean;
  /** Optional symmetric y error half-widths (same length as y); drawn as capped bars on points series. */
  readonly yErr?: Column;
}

/** A confidence band between lower and upper curves sharing the x column. */
export interface Band {
  readonly id: string;
  readonly label: string;
  readonly x: Column;
  readonly lower: Column;
  readonly upper: Column;
  readonly color?: string;
}

/** A fitted line (or curve) drawn dashed over the data. */
export interface FitLine {
  readonly id: string;
  readonly label: string;
  readonly x: Column;
  readonly y: Column;
  readonly color?: string;
}

/** Corner of the plot area for the annotation box; "auto" picks the corner that hides the least data. */
export type Anchor = "tl" | "tr" | "bl" | "br" | "auto";

/** Boxed text block (equations, fitted values with uncertainty). */
export interface AnnotationBox {
  readonly lines: readonly string[];
  readonly anchor?: Anchor;
}

/** Complete, pure description of a figure; the renderer and exporters only read this. */
export interface Scene {
  readonly width: number;
  readonly height: number;
  readonly title: string;
  readonly subtitle?: string;
  readonly footer?: string;
  readonly xAxis: AxisSpec;
  readonly yAxis: AxisSpec;
  readonly series: readonly Series[];
  readonly bands?: readonly Band[];
  readonly fits?: readonly FitLine[];
  readonly annotation?: AnnotationBox;
  readonly legend?: boolean;
  readonly theme: Theme;
}

/** Axis title as shown: "label (unit)" or just the label when unitless. */
export function axisTitle(axis: AxisSpec): string {
  return axis.unit === undefined || axis.unit === "" ? axis.label : `${axis.label} (${axis.unit})`;
}

/** Resolved colour for the i-th drawable, honouring an explicit override. */
export function pickColor(theme: Theme, index: number, explicit?: string): string {
  return explicit ?? theme.palette[index % theme.palette.length] ?? theme.text;
}
