import { api } from "@/lib/api";
import { Card, Empty, PageHeader, ChannelBadge, CostBadge } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function Methodology() {
  let meta;
  try {
    meta = await api.meta();
  } catch {
    return <Empty>Couldn’t reach the data API.</Empty>;
  }
  const st = meta.signalling_theory || {};

  return (
    <>
      <PageHeader
        title="Methodology"
        lead="How every number is computed and which literature justifies each choice. The signalling-theory model is the same YAML the AI agents classify against — single source of truth."
      />

      <Card style={{ borderLeft: "3px solid var(--accent)" }}>
        <h3 style={{ marginTop: 0 }}>Project goal</h3>
        <p style={{ fontWeight: 600, fontSize: "1.1em", marginBottom: "0.4rem" }}>
          Specify as little as possible. Get out as much as possible.
        </p>
        <p className="small muted" style={{ marginTop: 0 }}>
          (German original: <em>&ldquo;Spezifiziere möglichst wenig, krieg möglichst viel heraus.&rdquo;</em>)
        </p>
        <p className="small">
          The Ehrenthal four-signal scheme is given as the classification target; the actor list is
          given as the input. Everything else — which sources to consult, which extraction strategies
          to apply, which signals to drop as noise — is left to the two multi-agent systems. The
          thesis evaluates the gap between the two architectures along that wide degree of freedom.
          The signals an <a href="https://atlasti.com/de" target="_blank" rel="noreferrer">Atlas.ti</a>{" "}
          researcher would manually code are the ones the systems should ideally produce
          automatically; where they disagree is where the evaluation focuses.
        </p>
      </Card>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>The core proposition</h3>
        <p className="muted">{st.premise || "In markets with noncommensurable performance, actors and observers rely on observable signals."}</p>
        <p className="muted">{st.cost_principle}</p>
      </Card>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>The {meta.dimensions.length} signal dimensions (three axes)</h3>
        <p className="small muted" style={{ marginTop: 0 }}>
          Each signal is one dimension, on three literature-grounded axes: channel (capability vs
          legitimacy), cost (hard-to-fake-ness), and observability (public verifiability).
        </p>
        <table>
          <thead>
            <tr>
              <th>Dimension</th><th>Channel</th><th>Cost</th><th className="num">Weight</th><th>Observ.</th><th>Grounding</th>
            </tr>
          </thead>
          <tbody>
            {meta.dimensions.map((d) => (
              <tr key={d.key}>
                <td><strong>{d.label}</strong><div className="small faint">{d.description}</div></td>
                <td><ChannelBadge channel={d.channel} /></td>
                <td><CostBadge cost={d.signal_cost} /></td>
                <td className="num">{d.weight}</td>
                <td className="small muted">{d.observability}</td>
                <td className="small muted" style={{ maxWidth: 280 }}>{d.grounding}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>

      <Card style={{ marginTop: "1rem" }}>
        <h3 style={{ marginTop: 0 }}>The scores</h3>
        <table>
          <thead><tr><th>Score</th><th>Formula</th><th>Answers</th></tr></thead>
          <tbody>
            <tr><td><strong>Impact</strong></td><td className="small"><code>Σ (weight × confidence)</code></td><td className="small muted">How much an observer should update their view.</td></tr>
            <tr><td><strong>Credibility</strong></td><td className="small"><code>Σ (weight × confidence × cost_mult)</code></td><td className="small muted">Impact after discounting cheap talk.</td></tr>
            <tr><td><strong>Cheap-talk ratio</strong></td><td className="small"><code>low_cost / total</code></td><td className="small muted">Substituting positioning for evidence?</td></tr>
            <tr><td><strong>Authority</strong></td><td className="small"><code>(cap+1)/(cap+leg+2)</code></td><td className="small muted">Capability- vs legitimacy-driven.</td></tr>
            <tr><td><strong>Momentum</strong></td><td className="small"><code>signals_7d − prev_7d</code></td><td className="small muted">Accelerating or cooling.</td></tr>
            <tr><td><strong>Diversity</strong></td><td className="small"><code>distinct dimensions</code></td><td className="small muted">Broad vs narrow signalling.</td></tr>
          </tbody>
        </table>
        <p className="small faint">Cost multipliers: {Object.entries(meta.cost_classes).map(([k, v]) => `${k} ${v.multiplier}`).join(" · ")}.</p>
      </Card>

      <Card style={{ marginTop: "1rem", borderLeft: "3px solid var(--warn)" }}>
        <h3 style={{ marginTop: 0 }}>Limitations</h3>
        <p className="small">
          This is a Bachelor&rsquo;s-thesis prototype, not a production intelligence
          tool, and the numbers should be read accordingly. Coverage is bounded by
          what is publicly visible &mdash; arXiv, actor websites, and Google News,
          plus optional patent records. Activity behind paywalls, in private
          channels, or not indexed by these sources stays invisible, which
          systematically undercounts smaller or stealth actors. The cohort is a
          fixed list of roughly 40 Swiss quantum-computing organisations observed
          over a single evaluation window, so the results describe the Swiss
          ecosystem in 2026 and do not generalise to other deep-tech fields, other
          countries, or other time periods.
        </p>
        <p className="small">
          Every signal is classified automatically by large language models against
          the signalling-theory scheme above &mdash; not hand-coded by a human
          &mdash; so the scores are best-effort estimates rather than ground truth,
          and the line between a costly signal and cheap talk is ultimately a model
          judgement. Both AI systems run on free-tier models and free web-search
          backends that are rate-limited and non-deterministic, so a given day&rsquo;s
          run can miss signals or vary from the next. The two systems also differ in
          more than architecture (their prompts differ too), which makes the
          System&nbsp;A vs System&nbsp;B comparison illustrative rather than a
          controlled benchmark. Finally, one person designed the systems, the schema,
          and this evaluation &mdash; an independent evaluator was outside the thesis
          scope &mdash; so the dashboard reports <em>observable public signalling</em>
          {" "}and makes no claim about any actor&rsquo;s actual research capability,
          commercial success, or scientific quality.
        </p>
      </Card>

      {st.references && (
        <Card style={{ marginTop: "1rem" }}>
          <h3 style={{ marginTop: 0 }}>References</h3>
          <ul className="small muted">
            {st.references.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
          <p className="small faint">
            Schema version {meta.version}{meta.last_revised ? ` · revised ${meta.last_revised}` : ""}.
            Full code, prompts and disposition on{" "}
            <a href="https://github.com/annageiser/mas-deeptech-research" target="_blank" rel="noreferrer">GitHub</a>.
          </p>
        </Card>
      )}
    </>
  );
}
