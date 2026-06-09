import { api } from "@/lib/api";
import { Card, Empty, PageHeader } from "@/components/ui";

export const dynamic = "force-dynamic";

type SP = { searchParams: { days?: string } };

interface NewsItem {
  id: string;
  source_url: string;
  source_name: string;
  title: string;
  summary?: string | null;
  published_at?: string | null;
  fetched_at: string;
}

export default async function QuantumNews({ searchParams }: SP) {
  const days = Number(searchParams.days || "30");
  let items: NewsItem[] = [];
  let count = 0;
  try {
    const data = await fetch(
      `${process.env.API_INTERNAL_URL || "http://api-container-f:8000"}/api/industry-news?days=${days}&limit=200`,
      { cache: "no-store" }
    ).then((r) => r.json());
    items = data.items || [];
    count = data.count || 0;
  } catch {
    return <Empty>Couldn't reach the data API.</Empty>;
  }

  return (
    <>
      <PageHeader
        title="Worldwide quantum news"
        lead="General quantum-computing news from around the world — not attributed to any of the 40 Swiss actors. Useful for context: what's the global ecosystem talking about this week?"
      />

      <div className="small muted" style={{ marginBottom: "0.75rem" }}>
        {count} items in the last {days} days · sources include The Quantum Insider, Phys.org Quantum, Nature, ScienceDaily, Innovation Origins, Quantinuum
      </div>

      {!items.length ? (
        <Empty>
          No worldwide-news items yet. The industry-news collector cron may not have run, or all recent feed entries matched a Swiss actor (and went to <a href="/signals">/signals</a> instead).
        </Empty>
      ) : (
        <div className="grid cols-2" style={{ gap: "0.75rem" }}>
          {items.map((it) => (
            <Card key={it.id}>
              <div className="small faint" style={{ marginBottom: "0.25rem" }}>
                {it.source_name}
                {it.published_at ? ` · ${it.published_at.slice(0, 10)}` : ""}
              </div>
              <div style={{ fontWeight: 600, marginBottom: "0.35rem" }}>
                <a href={it.source_url} target="_blank" rel="noreferrer">
                  {it.title}
                </a>
              </div>
              {it.summary ? (
                <div className="small">{it.summary.slice(0, 280)}{it.summary.length > 280 ? "…" : ""}</div>
              ) : null}
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
