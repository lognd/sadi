/** Module logger factory: the only sanctioned sink for diagnostics (no console elsewhere). */
export type Level = "debug" | "info" | "warn" | "error";

export interface Logger {
  debug(msg: string, ctx?: Record<string, unknown>): void;
  info(msg: string, ctx?: Record<string, unknown>): void;
  warn(msg: string, ctx?: Record<string, unknown>): void;
  error(msg: string, ctx?: Record<string, unknown>): void;
}

/** Create a logger tagged with a module name, writing to the browser console. */
export function getLogger(name: string): Logger {
  const emit = (level: Level, msg: string, ctx?: Record<string, unknown>): void => {
    /* eslint-disable no-console -- single sink for the whole web app */
    console[level](`[${name}] ${msg}`, ctx ?? {});
    /* eslint-enable no-console */
  };
  return {
    debug: (m, c) => { emit("debug", m, c); },
    info: (m, c) => { emit("info", m, c); },
    warn: (m, c) => { emit("warn", m, c); },
    error: (m, c) => { emit("error", m, c); },
  };
}
