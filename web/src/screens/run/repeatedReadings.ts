// frob:ticket 01M72YKF3EN8RJX7RCH78JDPQC
/** Repeated-readings (Type A + instrument) standard uncertainty; mirrors Measured.from_readings in python/sadi/uncertainty/measured.py. */
import type { Result } from "../../api/result";
import { err, ok } from "../../api/result";

/** Two-sided 95% Student-t factors for dof 1..30. */
const T95: readonly number[] = [
  12.7062, 4.3027, 3.1824, 2.7764, 2.5706, 2.4469, 2.3646, 2.3060, 2.2622, 2.2281,
  2.2010, 2.1788, 2.1604, 2.1448, 2.1314, 2.1199, 2.1098, 2.1009, 2.0930, 2.0860,
  2.0796, 2.0739, 2.0687, 2.0639, 2.0595, 2.0555, 2.0518, 2.0484, 2.0452, 2.0423,
];

/** Two-sided 95% t factor for `dof` degrees of freedom (normal 1.96 beyond the table). */
export function t95(dof: number): number {
  return T95[dof - 1] ?? 1.96;
}

/** Summary of a set of repeated readings. */
export interface ReadingsSummary {
  readonly n: number;
  readonly mean: number;
  /** Sample standard deviation (0 for n = 1). */
  readonly sd: number;
  /** Expanded 95% uncertainty U = sqrt((t s / sqrt n)^2 + Uinst^2). */
  readonly u95: number;
}

/** Parse numbers separated by commas, spaces or newlines; Err names the bad token. */
export function parseReadings(text: string): Result<readonly number[], string> {
  const tokens = text.split(/[\s,;]+/).filter((t) => t !== "");
  if (tokens.length === 0) return err("Enter at least one reading.");
  const xs: number[] = [];
  for (const t of tokens) {
    const x = Number(t);
    if (!Number.isFinite(x)) return err(`"${t}" is not a number.`);
    xs.push(x);
  }
  return ok(xs);
}

/** Mean, sd and RSS of the t-scaled standard error with the instrument uncertainty `uInst` (same unit as the readings). */
export function summarizeReadings(xs: readonly number[], uInst: number): Result<ReadingsSummary, string> {
  const n = xs.length;
  if (n === 0) return err("Enter at least one reading.");
  if (!Number.isFinite(uInst) || uInst < 0) return err("Instrument uncertainty must be a non-negative number.");
  const mean = xs.reduce((a, b) => a + b, 0) / n;
  const sd = n > 1 ? Math.sqrt(xs.reduce((a, b) => a + (b - mean) ** 2, 0) / (n - 1)) : 0;
  const typeA = n > 1 ? (t95(n - 1) * sd) / Math.sqrt(n) : 0;
  return ok({ n, mean, sd, u95: Math.sqrt(typeA ** 2 + uInst ** 2) });
}
