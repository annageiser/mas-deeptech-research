import { api } from "@/lib/api";
import { Card, Stat, Empty, PageHeader } from "@/components/ui";
import { Scatter2D } from "@/components/charts";

export const dynamic = "force-dynamic";

type SP = { searchParams: { days?: string } };

export default async function Compare({ searchParams }: SP) {
  const days = Number(searchParams.days || "90");
  let c;
  try {
    c = await api.compare(days);
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }

  const A = c.per_system.masfactory;
  const B = c.per_system.hermes;
  const scatter = c.agreement.map((r) => ({ name: r.name, a: r.system_a_impact, b: r.system_b_impact }));

  const row = (label: string, a: React.ReactNode, b: React.ReactNode) => (
    <tr>
      <td className="muted">{label}</td>
      <td className="num">{a}</td>
      <td className="num">{b}</td>
    </tr>
  );

  // System B identity transition: rows tagged system='hermes' before
  // 2026-06-10 came from a pattern implementation; from that date the real
  // NousResearch CLI is used. The window slider below lets you exclude the
  // pattern-era rows by picking days <= today − 2026-06-10.
  const today = new Date();
  const transitionDate = new Date("2026-06-10T00:00:00Z");
  const daysSinceTransition = Math.max(
    1,
    Math.floor((today.getTime() - transitionDate.getTime()) / 86_400_000),
  );

  return (
    <>
      <PageHeader
        title="System A vs System B"
        lead="Two architectures, same task, same sources, same model. MASFactory is an orchestrated 7-agent graph; Hermes is a single agent loop with memory + skills. The interesting question is not which wins — it's where and why they diverge."
      />

      <Card style={{ marginBottom: "1rem", background: "var(--bg-subtle)" }}>
        <div className="small">
          <strong>Window:</strong> last {days} days.{" "}
          <a href={`/compare?days=${daysSinceTransition}`}>
            Restrict to post-2026-06-10 (real Hermes CLI only)
          </a>{" "}
          ·{" "}
          <a href="/compare?days=30">30d</a> · <a href="/compare?days=90">90d</a> ·{" "}
          <a href="/compare?days=365">1y</a>
        </div>
        <div className="small faint" style={{ marginTop: "0.4rem" }}>
          <em>Why this matters:</em> System B rows before 2026-06-10 came from a Python pattern
          implementation; from that date forward the real NousResearch hermes-agent CLI is used.
          See <a href="/methodology">methodology</a> § "System B" for the full identity
          transition, or restrict the window to compare only the real-CLI era.
        </div>
      </Card>

      <div className="grid cols-3">
        <Stat label="Agree on actor" value={c.agreement_counts.both} help="Actors both systems flagged with non-trivial impact." />
        <Stat label="Only System A" value={c.agreement_counts.only_a} />
        <Stat label="Only System B" value={c.agreement_counts.only_b} />
      </div>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Head-to-head</h3>
        <table>
          <thead>
            <tr><th>Metric</th><th className="num">System A · MASFactory</th><th className="num">System B · Hermes</th></tr>
          </thead>
          <tbody>
            {row("Runs (ok / error)", `${A.runs_ok} / ${A.runs_error}`, `${B.runs_ok} / ${B.runs_error}`)}
            {row("Signals collected", A.signals, B.signals)}
            {row("Distinct actors", A.actors, B.actors)}
            {row("Input tokens", A.input_tokens.toLocaleString(), B.input_tokens.toLocaleString())}
            {row("Output tokens", A.output_tokens.toLocaleString(), B.output_tokens.toLocaleString())}
            {row("Signals / 1k tokens", A.signals_per_1k_tokens ?? "—", B.signals_per_1k_tokens ?? "—")}
          </tbody>
        </table>
        <p className="small faint" style={{ marginBottom: 0 }}>
          Signals-per-1k-tokens is the thesis's "output quality per token cost" metric, simplified.
          A system yielding fewer but higher-quality signals looks worse here — pair with the
          methodology's recall-vs-precision discussion.
        </p>
      </Card>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>Per-actor impact agreement</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          Each point is an actor. On the diagonal = the two systems agree on its impact. Off-diagonal
          = they disagree.
        </p>
        {scatter.length ? (
          <Scatter2D data={scatter} xKey="a" yKey="b" xLabel="System A impact" yLabel="System B impact" refDiagonal />
        ) : (
          <div className="empty">Need at least one successful run from each system.</div>
        )}
      </Card>
    </>
  );
}
