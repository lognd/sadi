import { beforeEach, describe, expect, it } from "vitest";
import { useStore } from "./store";

describe("store", () => {
  beforeEach(() => {
    useStore.setState({ connection: "unknown", sessionId: null });
  });

  it("updates connection", () => {
    useStore.getState().setConnection("up");
    expect(useStore.getState().connection).toBe("up");
  });

  it("updates session id", () => {
    useStore.getState().setSessionId("s1");
    expect(useStore.getState().sessionId).toBe("s1");
  });
});
