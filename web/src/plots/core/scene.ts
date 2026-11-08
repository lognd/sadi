// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
// frob:ticket 01M6W7R3D3KT3NM6JETDDAPA9P
// frob:ticket 01M6WM4ZDY9EHM2BW9312B5SEY
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
  /** "log" draws decade ticks and needs strictly positive data (see validateScene); default "linear". */
  readonly scale?: "linear" | "log";
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

/** A single marker glyph at a data point, optionally with a collision-avoided text label. */
export interface PointMarker {
  readonly id: string;
  readonly x: number;
  readonly y: number;
  readonly kind: MarkerKind;
  readonly color?: string;
  readonly label?: string;
}

/** Free text label attached to a data point; placed so it avoids data, boxes and other labels. */
export interface PointLabel {
  readonly id: string;
  readonly x: number;
  readonly y: number;
  readonly text: string;
}

/** Shaded band across the whole plot on one axis (a limit, a region of interest). */
export interface Span {
  readonly id: string;
  readonly axis: "x" | "y";
  readonly from: number;
  readonly to: number;
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
  /** Further boxes, placed greedily in order into the corners that avoid data and earlier boxes. */
  readonly annotations?: readonly AnnotationBox[];
  readonly markers?: readonly PointMarker[];
  readonly labels?: readonly PointLabel[];
  readonly spans?: readonly Span[];
  readonly legend?: boolean;
  /** False hides x tick labels and the x title (inner sub-panels). Default true. */
  readonly xLabels?: boolean;
  /** Minimum left plot edge in px, so stacked panels can align their plot areas. */
  readonly plotLeft?: number;
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
