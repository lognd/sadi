// frob:ticket 01M72PGN6FQEXXCFGXA3EMAPTS
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

/** The on-screen terminal theme: black phosphor canvas, monospace ticks, colour-blind-safe palette (name kept for import sites). */
export const lightTheme: Theme = {
  name: "terminal",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
  background: "#0c130c",
  plotBackground: "#0c130c",
  text: "#7dff9a",
  mutedText: "#6cc784",
  axis: "#4fa468",
  grid: "#1d3a25",
  annotationFill: "#132013",
  annotationStroke: "#4fa468",
  // frob:ticket 01M6XB9EBAP0ZTTYAMG9NEG3KJ
  palette: ["#56b4e9", "#ff9f40", "#4ee0a0", "#f78fc0", "#f0e442", "#a9a9ff"],
  fontSize: { title: 16, subtitle: 12, label: 13, tick: 11, legend: 11, annotation: 11, footer: 10 },
  lineWidth: 1.5,
  fitWidth: 2,
  markerRadius: 3,
  bandOpacity: 0.28,
};

/** The export theme for SVG/PNG figures: white paper, dark ink and a sans stack that Word and Inkscape resolve. */
export const exportTheme: Theme = {
  ...lightTheme,
  name: "export",
  fontFamily: "Helvetica, Arial, sans-serif",
  background: "#ffffff",
  plotBackground: "#ffffff",
  text: "#1c1b17",
  mutedText: "#55514a",
  axis: "#3a372f",
  grid: "#dddddd",
  annotationFill: "#f4f4f4",
  annotationStroke: "#999999",
  palette: ["#0072b2", "#d55e00", "#009e73", "#b8588f", "#a86f00", "#2f87c0"],
  lineWidth: 1.25,
  fitWidth: 1.75,
  bandOpacity: 0.22,
};
