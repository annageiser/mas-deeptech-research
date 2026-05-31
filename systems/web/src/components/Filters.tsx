"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useCallback } from "react";

const SYSTEMS = [
  { key: "both", label: "Both" },
  { key: "masfactory", label: "System A" },
  { key: "hermes", label: "System B" },
];
const WINDOWS = [7, 30, 90, 180];

export default function Filters() {
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const system = sp.get("system") || "both";
  const days = sp.get("days") || "30";

  const setParam = useCallback(
    (key: string, value: string) => {
      const next = new URLSearchParams(sp.toString());
      if ((key === "system" && value === "both") || (key === "days" && value === "30")) next.delete(key);
      else next.set(key, value);
      const q = next.toString();
      router.push(q ? `${pathname}?${q}` : pathname);
    },
    [router, pathname, sp]
  );

  return (
    <div className="filters">
      <div className="seg" title="Which AI system's data to show">
        {SYSTEMS.map((s) => (
          <button key={s.key} className={system === s.key ? "active" : ""} onClick={() => setParam("system", s.key)}>
            {s.label}
          </button>
        ))}
      </div>
      <select value={days} onChange={(e) => setParam("days", e.target.value)} title="Time window">
        {WINDOWS.map((w) => (
          <option key={w} value={w}>
            Last {w} days
          </option>
        ))}
      </select>
    </div>
  );
}
