"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const GROUPS: { label: string; items: { href: string; icon: string; label: string }[] }[] = [
  {
    label: "Ecosystem",
    items: [
      { href: "/", icon: "⚛", label: "Overview" },
      { href: "/signalling", icon: "✶", label: "Signalling theory" },
      { href: "/leaderboard", icon: "🏆", label: "Impact leaderboard" },
      { href: "/ecosystem", icon: "🗺", label: "Ecosystem map" },
      { href: "/graph", icon: "🕸", label: "Knowledge graph" },
    ],
  },
  {
    label: "Drill down",
    items: [
      { href: "/actors", icon: "🔬", label: "Actors" },
      { href: "/compare", icon: "🆚", label: "System A vs B" },
      { href: "/signals", icon: "📊", label: "Signals" },
      { href: "/coverage", icon: "📡", label: "Coverage" },
    ],
  },
  {
    label: "Context",
    items: [
      { href: "/quantum-news", icon: "🌍", label: "Worldwide quantum news" },
    ],
  },
  {
    label: "Reference",
    items: [
      { href: "/reports", icon: "📄", label: "Reports" },
      { href: "/methodology", icon: "📐", label: "Methodology" },
    ],
  },
];

export default function Nav() {
  const path = usePathname();
  const isActive = (href: string) =>
    href === "/" ? path === "/" : path.startsWith(href);
  return (
    <nav className="sidebar">
      <div className="brand">
        <div className="brand-title">Swiss Quantum</div>
        <div className="brand-sub">Ecosystem signal intelligence</div>
      </div>
      {GROUPS.map((g) => (
        <div key={g.label}>
          <div className="nav-group-label">{g.label}</div>
          {g.items.map((it) => (
            <Link key={it.href} href={it.href} className={`nav-link${isActive(it.href) ? " active" : ""}`}>
              <span className="ico">{it.icon}</span>
              {it.label}
            </Link>
          ))}
        </div>
      ))}
      <div className="nav-group-label" style={{ marginTop: "1.5rem" }}>About</div>
      <div className="small faint" style={{ padding: "0 0.75rem", lineHeight: 1.5 }}>
        BSc thesis · Anna Geiser · FHNW. Two multi-agent systems harvest public
        signals daily; this site reads the shared database.
      </div>
    </nav>
  );
}
