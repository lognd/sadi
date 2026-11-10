// frob:ticket WW37VH5
/** Theme preference logic: pure helpers plus a tiny hook; the CSS design system keys off html[data-theme]. */
import { useCallback, useEffect, useState } from "react";
import { getLogger } from "../../api/log";

const log = getLogger("shell.theme");

/** localStorage key holding the manual theme choice. */
export const THEME_KEY = "sadi.theme";

/** A concrete theme. */
export type Theme = "light" | "dark";

/** Parse a stored value; anything unknown means "no manual choice". */
export function parseTheme(raw: string | null): Theme | null {
  return raw === "light" || raw === "dark" ? raw : null;
}

/** Resolve the effective theme: manual choice wins, else the OS preference. */
export function resolveTheme(stored: Theme | null, prefersDark: boolean): Theme {
  return stored ?? (prefersDark ? "dark" : "light");
}

/** The other theme. */
export function otherTheme(t: Theme): Theme {
  return t === "dark" ? "light" : "dark";
}

function readStored(): Theme | null {
  try { return parseTheme(window.localStorage.getItem(THEME_KEY)); } catch { return null; }
}

function prefersDark(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(prefers-color-scheme: dark)").matches;
}

/** Theme state hook: applies html[data-theme], persists manual toggles to localStorage. */
export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useState<Theme>(() => (typeof window === "undefined" ? "light" : resolveTheme(readStored(), prefersDark())));
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = useCallback(() => {
    const next = otherTheme(theme);
    log.info("theme toggled", { next });
    try { window.localStorage.setItem(THEME_KEY, next); } catch { log.warn("theme not persisted"); }
    setTheme(next);
  }, [theme]);
  return { theme, toggle };
}
