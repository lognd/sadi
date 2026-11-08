// frob:ticket 01M6XAASH92DG6W6GDJBJVWSNR
/** Plain-language text for a server "stopped" message, with what the operator should do next. */

const KNOWN: Readonly<Record<string, string>> = {
  device_fault: "The instrument stopped responding.",
  overload: "The load went past the instrument range.",
};

/** Build the message-line text for a stop; `pointIndex` null means no point was captured yet in this step. */
export function stopText(reason: string, hint: string, pointIndex: number | null): string {
  const what = KNOWN[reason] ?? `The run stopped (${reason}).`;
  const next = reason === "device_fault"
    ? "Check the cable and power, then open Doctor to test the connection. Saved data is safe."
    : hint.trim();
  const zero = pointIndex === null ? " No points were captured in this step, so nothing was advanced: capture a point first, then continue." : "";
  return `${what} ${next}${zero}`.replace(/\s+/g, " ").trim();
}
