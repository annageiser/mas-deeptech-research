import Link from "next/link";
import { PageHeader, Card } from "@/components/ui";
import { PERSONA_LIST } from "@/lib/personas";

export const dynamic = "force-dynamic";

type SP = { searchParams: { system?: string; days?: string } };

export default function PersonasIndex({ searchParams }: SP) {
  const qs = new URLSearchParams();
  if (searchParams.system && searchParams.system !== "both") qs.set("system", searchParams.system);
  if (searchParams.days) qs.set("days", searchParams.days);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";

  return (
    <>
      <PageHeader
        title="Stakeholder lenses"
        lead="The same descriptive signal map, framed for the question you're actually asking. Pick a lens: it re-orders the metrics, surfaces the insight patterns that matter to you, and pre-sets the filters — all over one shared, source-attributed dataset."
      />

      <div className="grid cols-2">
        {PERSONA_LIST.map((p) => (
          <Link key={p.id} href={`/personas/${p.id}${suffix}`} style={{ textDecoration: "none", color: "inherit" }}>
            <Card style={{ borderLeft: `3px solid ${p.accent}`, height: "100%" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.35rem" }}>
                <span style={{ fontSize: "1.5rem" }} aria-hidden>{p.icon}</span>
                <h3 style={{ margin: 0 }}>{p.label}</h3>
              </div>
              <p className="small muted" style={{ margin: "0 0 0.5rem" }}>{p.tagline}</p>
              <p className="small" style={{ margin: 0 }}>{p.blurb}</p>
              <p className="small" style={{ margin: "0.6rem 0 0", color: p.accent, fontWeight: 600 }}>
                Open lens →
              </p>
            </Card>
          </Link>
        ))}
      </div>

      <p className="small faint" style={{ marginTop: "1rem" }}>
        Every lens is descriptive: it re-composes signals that are already collected and always shows the
        source evidence. It makes no investment, subsidy, or strategic recommendation. See the{" "}
        <Link href="/methodology">methodology</Link> for how each number is computed.
      </p>
    </>
  );
}
