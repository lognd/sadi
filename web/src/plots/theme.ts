// frob:ticket 01M6W7R383ZG0WZNNVJMQYWW87
/** Plot theme: every colour, font and stroke the renderer uses, so scenes never hard-code style. */
export interface Theme {
  readonly name: string;
  readonly fontFamily: string;
  readonly background: string;
  readonly plotBackground: string;
  readonly text: string;
  readonly mutedText: string;
  readonly axis: string;
  readonly grid: string;
  readonly annotationFill: string;
  readonly annotationStroke: string;
  /** Series colours, cycled by series index when a series sets none. */
  readonly palette: readonly string[];
  readonly fontSize: {
    readonly title: number;
    readonly subtitle: number;
    readonly label: number;
    readonly tick: number;
    readonly legend: number;
    readonly annotation: number;
    readonly footer: number;
  };
  readonly lineWidth: number;
  readonly fitWidth: number;
  readonly markerRadius: number;
  readonly bandOpacity: number;
}

/** The default light, print-friendly theme (ASCII-safe font stack, colour-blind-safe palette). */
export const lightTheme: Theme = {
  name: "light",
  fontFamily: "Helvetica, Arial, sans-serif",
  background: "#ffffff",
  plotBackground: "#ffffff",
  text: "#111111",
  mutedText: "#555555",
  axis: "#333333",
  grid: "#e3e3e3",
  annotationFill: "#fafafa",
  annotationStroke: "#999999",
  // frob:ticket 01M6XB9EBAP0ZTTYAMG9NEG3KJ
  palette: ["#0072b2", "#d55e00", "#009e73", "#b8588f", "#a86f00", "#2f87c0"],
  fontSize: { title: 16, subtitle: 12, label: 13, tick: 11, legend: 11, annotation: 11, footer: 10 },
  lineWidth: 1.5,
  fitWidth: 1.75,
  markerRadius: 3,
  bandOpacity: 0.22,
};
