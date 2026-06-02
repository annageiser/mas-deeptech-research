"use client";

import { useEffect, useState } from "react";

/**
 * Theme toggle for the public site. Tri-state cycle: auto → light → dark → auto.
 *
 *   - "auto"  → no data-theme attribute on <html>; CSS prefers-color-scheme
 *               media query in globals.css decides.
 *   - "light" → data-theme="light" on <html>; explicitly overrides the OS.
 *   - "dark"  → data-theme="dark" on <html>; explicitly overrides the OS.
 *
 * Persisted to localStorage["mas-theme"]. An inline pre-mount script in
 * layout.tsx reads the same key BEFORE React hydration so the chosen
 * theme paints on first frame (no light-then-dark flash).
 */

type Theme = "auto" | "light" | "dark";

const STORAGE_KEY = "mas-theme";

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  if (theme === "auto") {
    root.removeAttribute("data-theme");
  } else {
    root.setAttribute("data-theme", theme);
  }
}

function readStoredTheme(): Theme {
  if (typeof window === "undefined") return "auto";
  const v = window.localStorage.getItem(STORAGE_KEY);
  if (v === "light" || v === "dark" || v === "auto") return v;
  return "auto";
}

export default function ThemeToggle() {
  // Render a placeholder during SSR to avoid hydration mismatch — the real
  // chosen theme is unknown server-side. We mount the icon on the client.
  const [mounted, setMounted] = useState(false);
  const [theme, setTheme] = useState<Theme>("auto");

  useEffect(() => {
    const t = readStoredTheme();
    setTheme(t);
    setMounted(true);
  }, []);

  function cycle() {
    const next: Theme = theme === "auto" ? "light" : theme === "light" ? "dark" : "auto";
    setTheme(next);
    applyTheme(next);
    try {
      if (next === "auto") window.localStorage.removeItem(STORAGE_KEY);
      else window.localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // localStorage might be blocked (e.g. Safari private mode) — silently ok.
    }
  }

  const icon = !mounted ? "·" : theme === "dark" ? "◐" : theme === "light" ? "☀" : "⌂";
  const label = !mounted ? "" : theme === "auto" ? "Auto" : theme === "light" ? "Light" : "Dark";

  return (
    <button
      type="button"
      className="theme-toggle"
      onClick={cycle}
      title={`Theme: ${label} (click to cycle: auto → light → dark)`}
      aria-label={`Theme: ${label}, click to change`}
    >
      <span className="ico" aria-hidden>{icon}</span>
      <span>{label}</span>
    </button>
  );
}
