// frob:ticket 01M71SKWW36NDBJK24QD7DHSW4
/** Translate server repr strings (ComputeCode.X, enum names) into plain language with a next action. */

const CODES: Readonly<Record<string, string>> = {
  TOO_FEW_POINTS: "Not enough captured points yet - go back to the Elastic run step and capture at least 3 points.",
  NO_POINTS: "Nothing has been captured yet - capture at least 3 settled points in the Elastic run step.",
  SINGULAR: "The points do not spread enough to fit a line - capture points at clearly different loads.",
  DEGENERATE: "The points do not spread enough to fit a line - capture points at clearly different loads.",
};

/** Plain-language text for a server note or error; unknown text passes through with enum reprs stripped. */
export function plainNote(raw: string): string {
  const m = /(?:ComputeCode\.)?([A-Z][A-Z_]{3,})/.exec(raw);
  const known = m?.[1] === undefined ? undefined : CODES[m[1]];
  if (known !== undefined) return known;
  if (/code=|ComputeCode\./.test(raw)) {
    const detail = /detail='([^']*)'/.exec(raw)?.[1];
    return `The analysis could not finish${detail === undefined ? "" : ` (${detail})`} - check your captured points, then try again.`;
  }
  return raw;
}
