import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import Nav from "@/components/Nav";
import Filters from "@/components/Filters";
import ThemeToggle from "@/components/ThemeToggle";

export const metadata: Metadata = {
  title: "Swiss Quantum Ecosystem · Signal Intelligence",
  description:
    "Who has impact in Swiss quantum computing, what signals they send, and how their position shifts — harvested daily from public sources. BSc thesis, Anna Geiser, FHNW.",
};

/**
 * Inline pre-mount theme script. Runs BEFORE React hydrates so the chosen
 * theme is on <html> when the first paint happens — no light-then-dark
 * flash on dark-mode loads. The script reads localStorage["mas-theme"]
 * and sets data-theme on <html> accordingly. If no choice is stored,
 * the data-theme attribute stays absent and globals.css's
 * prefers-color-scheme media query decides.
 */
const themeBootstrapScript = `(function(){try{var t=localStorage.getItem("mas-theme");if(t==="dark"||t==="light"){document.documentElement.setAttribute("data-theme",t);}}catch(e){}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
      </head>
      <body>
        <div className="app">
          <Nav />
          <div className="main">
            <header className="topbar">
              <div className="small muted">
                Live · updated daily 02:00 &amp; 05:00 CET
              </div>
              <div style={{ display: "flex", gap: "0.75rem", alignItems: "center" }}>
                <Suspense fallback={<div className="filters" />}>
                  <Filters />
                </Suspense>
                <ThemeToggle />
              </div>
            </header>
            <main className="content">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
