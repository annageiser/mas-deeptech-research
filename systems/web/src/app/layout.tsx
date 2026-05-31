import type { Metadata } from "next";
import { Suspense } from "react";
import "./globals.css";
import Nav from "@/components/Nav";
import Filters from "@/components/Filters";

export const metadata: Metadata = {
  title: "Swiss Quantum Ecosystem · Signal Intelligence",
  description:
    "Who has impact in Swiss quantum computing, what signals they send, and how their position shifts — harvested daily from public sources. BSc thesis, Anna Geiser, FHNW.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="app">
          <Nav />
          <div className="main">
            <header className="topbar">
              <div className="small muted">
                Live · updated daily 02:00 &amp; 05:00 CET
              </div>
              <Suspense fallback={<div className="filters" />}>
                <Filters />
              </Suspense>
            </header>
            <main className="content">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
