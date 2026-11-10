// frob:ticket 01M71RCHHEM9EKV4SAEYTVC4WD
// frob:accept COV001 because="vitest tests; TypeScript test discovery needs grimble, not installed here"
import { renderToString } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { StreamHandle } from "../ws/client";
import { LiveProvider, useLive } from "./LiveContext";

function Probe({ tag }: { readonly tag: string }): React.JSX.Element {
  const { view } = useLive();
  return <i data-tag={tag}>{view.source}</i>;
}

describe("LiveProvider", () => {
  it("throws a clear error when used outside a provider", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() => renderToString(<Probe tag="a" />)).toThrow(/LiveProvider/);
    spy.mockRestore();
  });

  it("gives every consumer the same provider feed", () => {
    const open = vi.fn((): StreamHandle => ({ close: () => undefined }));
    const out = renderToString(<LiveProvider trace={{ open }}><Probe tag="a" /><Probe tag="b" /></LiveProvider>);
    expect(out.match(/<i /g)?.length).toBe(2);
  });

  it("forces the Simulated source when asked", () => {
    const html = renderToString(<LiveProvider simulated trace={{ open: () => ({ close: () => undefined }) }}><Probe tag="a" /></LiveProvider>);
    // SSR has no open connection yet, so the source is Disconnected until the socket opens.
    expect(html).toContain("disconnected");
  });
});
