import { afterEach, expect, it, vi } from "vitest";
import { getLogger } from "./log";

afterEach(() => {
  vi.restoreAllMocks();
});

/** Messages are tagged with the module name and carry their context. */
function tagsMessagesWithModuleName(): void {
  const spy = vi.spyOn(console, "info").mockImplementation(() => undefined);
  getLogger("mod").info("hello", { a: 1 });
  expect(spy).toHaveBeenCalledWith("[mod] hello", { a: 1 });
}

it("tags messages with the module name", tagsMessagesWithModuleName);
