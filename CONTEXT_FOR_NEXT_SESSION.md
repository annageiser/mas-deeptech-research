# Context for the next session

A complete handover. If you are a fresh Claude session or a new collaborator,
read this from top to bottom once. It will give you enough to act on
without having to re-derive the past months of decisions from the
commit log.

---

## At a glance

This is the **BSc-thesis repository of Anna Geiser** (FHNW Brugg-Windisch,
supervisor Prof. Dr. Joachim Ehrenthal, submission deadline 2026-08-07).
It implements and empirically compares **two multi-agent systems** that
map the Swiss quantum-computing ecosystem under noncommensurable
performance, using the four-signal coding scheme of Ehrenthal et al.
(2026).

- **System A (MASFactory)** — explicit-graph orchestration, seven named
  agents, declared edges, per-actor loop. Built on Liu et al. (2026)
  MASFactory framework.
- **System B (Hermes)** — NousResearch Hermes Agent CLI in a thin
  Docker wrapper, autonomous single-loop agent with skills and tools.

Both systems run daily on the same Hostinger VPS, write to the same
Supabase database, surface their output through the same public Next.js
dashboard at <https://mas-deeptech-research.cloud>, and are compared
empirically in the thesis's Chapter 3 + Chapter 4.

The empirical work has been live since 2026-05. The thesis body
(~11,193 words across §1–§5) was drafted by Claude across multiple
sessions and lives in
`/Users/annageiser/Library/CloudStorage/OneDrive-FHNW/01 Studium/Bachelor Thesis/Bachelor Thesis - Anna Geiser/Bachelor_Thesis_Geiser_Anna.docx`.

---

## Thesis understanding

### Title

> Multi-Agent Systems for Ecosystem Mapping Under Noncommensurable
> Performance — Computational Signal Processing in Swiss Quantum
> Computing

### People + dates

- Author: Anna Geiser (anna.maria.geiser29@gmail.com)
- Supervisor: Prof. Dr. Joachim Ehrenthal (FHNW HSW)
- Institution: Fachhochschule Nordwestschweiz (FHNW), School of Business
- Submission: 2026-08-07
- Today's date when handing over: 2026-06-23

### Central research question

> How does the architectural choice of a multi-agent system shape its
> ability to surface nontechnical signals about quantum-computing
> vendors operating in a market where performance is noncommensurable?

### Four subordinate questions (in the order §4.1.2 answers them)

1. Which architecture has the larger effect on signal yield over a
   fixed window?
2. Which has the larger effect on the four-signal mix?
3. Which produces fewer attribution errors on a hand-coded gold set?
4. Which delivers more signals per unit token cost?

### Theoretical frame

- **Signalling theory** — Suchman (1995), Spence's costly-signalling
  baseline.
- **Operationalised for quantum** — Ehrenthal et al. (n.d.), four
  signal types: `legitimacy`, `customer_cocreation`,
  `community_ecosystem`, `future_trajectory`, with two boolean flags
  `defense_engagement` + `defense_ambivalence` overlaid on top
  (Connelly 2011 + Eisenberg 1984 strategic ambiguity).
- **Method** — design-science / constructive research (Kasanen, Lukka,
  Siitonen 1993; Shaw 2001). Builds an artefact, evaluates against
  pre-registered criteria.

### Contribution claim (as drafted in §5.2)

The work makes **one methodological + one practical contribution**:
- Methodological: demonstrates that a multi-agent system can be
  evaluated against a content-analysis gold standard drawn from
  ATLAS.ti / QualCoder, and that a two-system comparison sharing one
  database makes architectural choices empirically tractable.
- Practical: provides the Swiss quantum ecosystem with a continuously
  refreshed map of forty seeded actors, publicly accessible at
  mas-deeptech-research.cloud.

Secondary contributions: the iteration log, threats-to-validity
document, pre-registration of evaluation metrics, lessons-learned
record, and open-source release.

---

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                  Hostinger VPS — Ubuntu 24.04                       │
│              4 vCPU · 16 GB RAM · 100 GB SSD · no GPU               │
│                                                                     │
│   docker compose stack (7 services)                                 │
│   ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐   │
│   │ masfactory       │  │ hermes           │  │ reports         │   │
│   │ (System A)       │  │ (System B)       │  │ (daily +        │   │
│   │ cron-driven      │  │ cron-driven      │  │  weekly md)     │   │
│   │ 04:00 Zurich     │  │ 05:00 Zurich     │  │ chained on cron │   │
│   └────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘   │
│            │                     │                     │            │
│            └─────────┬───────────┘                     │            │
│                      ▼                                 ▼            │
│             Supabase (Postgres + pgvector)                          │
│             public.signals, public.actors, public.runs, ...         │
│                      ▲                                              │
│                      │                                              │
│   ┌──────────────────┴──────────────────┐                           │
│   │  api  (FastAPI)  ←  web  (Next.js) ← caddy (TLS + basic-auth)  │
│   └─────────────────────────────────────┘                           │
│                                                                     │
│   Optional: phoenix (Arize tracing) behind compose profile          │
└─────────────────────────────────────────────────────────────────────┘
```

### Data flow (one daily cron tick)

1. Host cron fires `docker compose run --rm masfactory` (System A)
   or `… hermes` (System B) at 04:00 / 05:00 Europe/Zurich.
2. The container reads `data/raw/actors.yaml` (40 actors).
3. For each actor, the agent(s) call external sources: arXiv API,
   actor websites, Google News (System A) or web_search/skills
   (System B), EPO Open Patent Services, press aggregator.
4. Signal candidates pass through classification + critic + dedup +
   actor-attribution gates.
5. Surviving signals get written to `public.signals` with
   `system = 'masfactory'` or `system = 'hermes'`.
6. The `reports` service generates a daily markdown briefing per
   system, also chained from cron.
7. The public dashboard at mas-deeptech-research.cloud reads from
   Supabase via the FastAPI service and renders on every page-view.

### Key contracts

- **Schema parity**: both systems write to the SAME `public.signals`
  table with the SAME columns, distinguished only by `system`.
- **Source-code isolation**: System B's persister has NO Python
  imports from `masfactory_system` — the "comparison-validity
  invariant." Otherwise differences could trace to shared code rather
  than to architecture.
- **Free-tier-only LLM policy** (relaxed v0.4.36): every model the
  systems use is on OpenRouter's free tier OR costs ≤ ~$3/month at
  daily-cron volume. After v0.4.36, System B uses paid Mistral Nemo
  at ~$0.30/month because every free-tier 70B-class model failed in
  one of six identified ways.

---

## Systems and modules

### Repository top-level

```
mas-deeptech-research/
├── CONTEXT_FOR_NEXT_SESSION.md  ← this file
├── README.md
├── .env.example                  ← documented env vars (per-service)
├── docker-compose.yml            ← 7-service stack
├── caddy/Caddyfile               ← TLS + basic-auth gating
├── data/
│   ├── raw/actors.yaml           ← 40 Swiss-quantum actors (fixed for the eval window)
│   ├── raw/rss_feeds.yaml        ← Quantum Insider + similar RSS sources
│   ├── raw/thesis_notes.md       ← Anna's own free-form notes
│   └── reports/                  ← generated daily/weekly markdown
├── systems/
│   ├── masfactory/               ← System A
│   ├── hermes/                   ← System B
│   ├── reports/                  ← daily + weekly report generator
│   ├── api/                      ← FastAPI read-only JSON
│   ├── web/                      ← Next.js 14 frontend
│   ├── dashboard/                ← legacy Streamlit (kept during cutover)
│   └── evaluation/               ← evaluation harness
├── docs/                         ← see "Key docs" below
└── .github/workflows/ci.yml      ← pytest + tsc + Docker build-check
```

### Inside each system

| Service | Language | Role | Key files |
|---|---|---|---|
| **masfactory** | Python | Graph-orchestrated 7-agent pipeline | `masfactory_system/agents/{planner,retriever,extractor,classifier,critic,critic_consensus,critic_debate,reranker_prefilter,analyst,persistence,loop_nodes}.py`, `graph.py`, `runner.py`, `classification/schema.yaml` |
| **hermes** | Bash + Python | Wraps `nousresearch/hermes-agent:v2026.6.5` Docker image | `Dockerfile`, `scripts/collect_all_actors.sh` (cron entrypoint), `scripts/persist_signals.py` (Supabase upsert), `skills/collect-swiss-quantum-signals/SKILL.md` (agent's methodology prompt) |
| **reports** | Python | Reads Supabase + git, generates markdown daily/weekly | `reports_system/{daily,weekly_system,weekly_thesis}.py`, `reports_system/supabase_reader.py`, `prompts/*.md` |
| **api** | Python FastAPI | Read-only JSON over Supabase | `api_app/{main,data_access,coverage,knowledge_graph,scoring,reports,meta,labels}.py` |
| **web** | TypeScript / Next.js 14 | Public dashboard | `src/app/*/page.tsx` (11 pages), `src/components/{Nav,charts,ui,GraphCanvas,ThemeToggle}.tsx`, `src/lib/{api,types}.ts` |

### System A's per-actor loop (graph)

```
ENTRY → Planner → Retriever → ActorLoop(
                                PrepareCurrentActor →
                                Extractor →
                                Classifier →
                                RerankerPreFilter (v0.4.23, pass-through when off) →
                                Critic [or consensus + debate chain] →
                                AccumulateActor
                              ) → Analyst → Persistence → EXIT
```

Critic has three modes selectable by env:
- Mode A (default): single-pass Critic
- Mode B (`MASF_CRITIC_CONSENSUS_PASSES=3`): three independent
  passes + majority vote (Wang et al. 2023 self-consistency)
- Mode C (B + `MASF_CRITIC_DEBATE_ROUNDS=1`): adds Du et al. 2023
  multi-agent debate round before vote

### System B's per-actor loop (script)

```
collect_all_actors.sh (bash):
  for each actor in actors.yaml:
    prompt = "use the collect-swiss-quantum-signals skill ..."
    hermes chat --skills collect-swiss-quantum-signals,arxiv,blogwatcher \
                --toolsets web,skills \
                --model "$HERMES_MODEL" \
                --provider openrouter \
                -q "$prompt" → JSON output
    persist_signals.py parses + upserts to Supabase
```

The skill `collect-swiss-quantum-signals/SKILL.md` is what makes the
agent specialise on the Swiss-quantum task. Bundled skills (`arxiv`,
`blogwatcher`) come from the upstream Hermes image's 74-skill catalogue.

---

## Important findings

### Empirical (from the daily comparison)

1. **System A produces more total signals** because its planner
   schedules every actor every day; System B's autonomous planner
   truncates low-signal actors after an unproductive search.
2. **System A produces more legitimacy signals** because its
   retriever explicitly queries arXiv + EPO patents. System B reaches
   these sources only when the agent's open planning happens to.
3. **System A has higher precision via a structural actor-attribution
   gate**; System B has comparable recall via more open search reach.
4. **Same model can produce wildly different outcomes in the two
   systems** (see "model-parser robustness" below) — the architecture
   choice shapes which models the system can robustly consume. This is
   the strongest finding for the central RQ and is documented in
   §4.1.2 paragraph 4 of the thesis.

### Methodological / lessons-learned

Captured in `docs/lessons-learned.md` (§2.1 through §2.11). The
recurring patterns:

- **Free-tier infrastructure is a finding, not just a constraint**
  — OpenRouter's free-tier behaviour (rate limits, model retirements,
  reasoning-wrapper bugs, missing tool support) generated more
  documented incidents than any single architectural decision.
- **The schema is the thesis** — by treating
  `classification/schema.yaml` as a single source of truth between
  the masfactory agents, the persister, the API, and the web frontend,
  every later refactor (Ehrenthal v0.4.0, defense-flags v0.4.19,
  sentiment v0.4.24, …) propagated automatically.
- **Caddy `caddy reload` doesn't apply changes** — use
  `docker compose restart caddy`. Wasted ~3 h debugging phantom
  Caddyfile syntax issues.
- **Docker BuildKit COPY-layer cache can lie** — script changes that
  should invalidate sometimes don't. Use `--no-cache` or surgical
  `git checkout origin/<branch> -- <file>`.
- **VPS branch-state divergence is invisible at the file level** —
  `git pull` can say "Already up to date" while your work sits on a
  different branch the VPS doesn't track. Run
  `git branch --show-current` first.
- **Framework edges declare keys; nodes must emit them** —
  `build-check` only validates compilation, not edge-key
  satisfaction. A v0.4.23 edge-key mismatch would have crashed every
  cron tick the next morning if the Phoenix smoke hadn't surfaced it.

### Today's debug saga — the "model-roulette" (2026-06-22 → 23)

Worth recording because it's the load-bearing operational story behind
the v0.4.27–v0.4.36 chain:

System B had been producing `signals: []` for every actor for the
entire evaluation window. Diagnostics surfaced these eight failure
modes in sequence, each one revealing the next layer:

1. **Skill-list mismatch** (v0.4.26b) — `company-research`,
   `scrapling` skill names existed in our local Hermes build but not
   in the official v2026.6.5 image. Fixed by trimming to known-good
   skills.
2. **Misleading error message** (v0.4.26a) — error pointed at a
   persist.log that never gets written when all actors fail at the
   agent level.
3. **`cd /opt/mas-deeptech-research`** ran inside a nested SSH
   session — one of several human-side mis-paste errors during
   debugging.
4. **TSV IFS field-collapse** (v0.4.28) — `IFS=TAB read -r slug name
   aliases website category` collapsed empty middle fields on the
   production container, so `Category` ended up in the prompt's
   `Website` field. Fixed by switching to `cut -f` extraction.
5. **Reasoning-wrapper bug** — Nemotron Super 120B :free wraps all
   output in `<think>` tokens; Hermes's response parser can't unwrap
   them; visible body is empty; persister sees `signals: []`. Same
   bug bit `openai/gpt-oss-120b:free` later.
6. **HERMES_MODEL env override didn't reach the container** (v0.4.30)
   — docker-compose.yml's environment block didn't pass it through.
7. **Free-tier rate limits** (Llama 3.3 70B :free upstream-provider
   Venice 429s within seconds) — adding $10 OpenRouter credit
   unlocked higher rate limits but didn't help when the model was
   served only via the rate-limited free endpoint.
8. **Free-tier model retirements** — `qwen/qwen-2.5-72b-instruct:free`
   and `mistralai/mistral-nemo:free` were moved from free to paid
   during the debugging session. `google/gemini-2.0-flash-001` had
   been retired entirely.
9. **Tool-calling not supported on free providers** —
   `nousresearch/hermes-3-llama-3.1-405b:free` was free but no free
   provider exposed tool-calling.

Resolution (v0.4.36): switched to **`mistralai/mistral-nemo` PAID**
at $0.02/M input + $0.03/M output ≈ **$0.30/month**. First smoke
produced 4 real signals for swiss-quantum-initiative including the
ETH Zurich qubit-surgery story the search backend had been returning
all along. End of saga.

The whole sequence is documented in the iteration docs
`docs/iterations/v0.4.26-…` through `v0.4.36-…` and was the basis for
the new §4.1.2 paragraph on architecture-attributable
model-parser robustness.

---

## Current conclusions (as drafted in §5.1)

1. **Architectural choices in multi-agent systems have observable
   behavioural consequences on a noncommensurable-performance
   intelligence task, and the consequences are interpretable in the
   marketing literature's existing four-signal vocabulary.**
   Explicit-graph (System A) trades flexibility for auditability and
   coverage breadth. Open-loop agent (System B) trades auditability
   for efficient depth on high-signal actors. Neither dominates.
2. **Free-tier LLM inference + free search backends + a small VPS are
   jointly sufficient** to operate a continuously-running ecosystem-
   mapping system. The binding resource is operator attention, not
   infrastructure cost. Updated after v0.4.36: ~$3/month of paid
   model inference is the realistic operating cost once free-tier
   instability is honestly accounted for.
3. **The Ehrenthal et al. (n.d.) four-signal coding scheme survives
   operationalisation as a machine-readable taxonomy with limited
   modification** — two extension sub-dimensions (`funding_event`,
   `regulatory_recognition`) and the v0.4.19 conversion of defence
   from a 5th signal_type to boolean flags. The compatibility of the
   ATLAS.ti / QualCoder manual-coding tradition with the automated
   implementation is evidence that the gap between content-analysis
   research and multi-agent automation can be narrowed in practice.

---

## Open questions (need Anna's input)

These are pending tasks where the next step requires Anna's judgement
or her manual work, not more code:

| ID | Topic | What's blocking |
|---|---|---|
| #98 (A.1) | Two-tier login (admin + user roles) | Auth design decision; needs scope agreement |
| #102 (C.1) | Gold-standard human coding | Anna's parallel manual labelling in ATLAS.ti |
| #105 (D.1) | Defense-ambivalence phenomenon research | Thesis-level literature reading |
| #108 (E.1) | Learning loop | Depends on #102 gold set |
| #109 (F.1) | Stakeholder persona views | UX design call |
| #110 (F.2) | Stock validator (yfinance) | Research call |
| #111 (G.1) | GitHub audit (continuous) | Ongoing research |
| #114 (S.3) | Signal-judgement page (admin) | UX scope |
| #115 (S.4) | Human-in-the-loop page | UX scope |
| #116 | Mobile adaptability | Design call |

Everything technically shippable without Anna is done. The remaining
"open" issues are research / writing / design decisions.

---

## Assumptions

These are quiet premises that the entire repo rests on. If any
becomes false, large rewrites would follow.

- **Both systems run on the same Hostinger VPS** (Ubuntu 24.04, 4 vCPU,
  16 GB RAM, 100 GB SSD, no GPU). Sizing is the constraint behind the
  "no local Ollama" decision and the "must use cloud LLM" framing.
- **OpenRouter remains the LLM gateway**. If OpenRouter shuts down or
  deprecates the chosen model, fall back to direct provider APIs
  (Anthropic, OpenAI, Google) — change is small but requires
  `--provider <name>` in the Hermes invocation and a separate API key.
- **Supabase free tier remains sufficient** for the project's data
  volume (~thousands of signal rows). If exceeded, the schema can move
  to any standard Postgres host with pgvector.
- **Forty actors are the universe**. Adding actors mid-evaluation
  would confound system-attributable yield differences with
  corpus-attributable differences. The list is frozen.
- **All sources are public + free**. Paid services (Tavily, Firecrawl,
  EPO OPS paid tier) were considered and explicitly rejected for
  reproducibility and budget reasons. ddgs / EPO OPS free tier are
  enough.
- **Anna is the sole evaluator** for the gold-standard coding
  (#102). The single-coder limitation is acknowledged in §4.1.4.
- **Submission date 2026-08-07** is the hard deadline.

---

## Remaining tasks

Source of truth: TaskList in this repo's session state OR
`docs/backlog.md` for the strategic / MoSCoW view.

Quick view of pending items as of handover:

```
A.1  pending   Two-tier login (auth design)
C.1  pending   Gold-standard human coding (Anna's manual work)
D.1  pending   Defense-ambivalence research (Anna's reading)
E.1  pending   Learning loop (depends on C.1)
F.1  pending   Stakeholder persona views (design call)
F.2  pending   Stock validator integration (research call)
G.1  pending   GitHub audit (ongoing)
S.3  pending   Admin judgement page (UX scope)
S.4  pending   Human-in-the-loop page (UX scope)
C.2  pending   Mobile adaptability (design)
```

All of these need Anna's input before code can move. **There is no
backlog item shippable without her.**

---

## Key files and their purpose

### Documentation (must-read for context)

| File | What it is |
|---|---|
| `docs/architecture.md` | Mermaid diagram + per-service description |
| `docs/methodology.md` | Design-science framing, project goal statement |
| `docs/reproducibility.md` | Hostinger VPS runbook (Phase 0 → Phase 5) |
| `docs/migrations.md` | Every SQL migration with rationale + verification query |
| `docs/signal-taxonomy.md` | Thesis-citable reference for the Ehrenthal four-signal scheme + 19 sub-categories |
| `docs/pre-registration.md` | Evaluation protocol committed before any data was looked at |
| `docs/threats-to-validity.md` | Acknowledged limits (with §-numbers cross-referenced to the thesis) |
| `docs/lessons-learned.md` | 11 production-engineering + methodological lessons captured per incident |
| `docs/backlog.md` | MoSCoW backlog + Bugs + Hermes-skills + Strategic A-I + Will-Not-Have |
| `docs/iterations/*.md` | One doc per shipped version (v0.4.4 → v0.4.36) — design rationale, implementation changes, runbook, threats-to-validity touched |
| `docs/session_log.md` | One row per assistant working session, with date, model, summary |
| `docs/open-questions.md` | Anna's open questions for supervisor / herself |
| `docs/wrong-signals-strategy.md` | The three-workflow ladder for handling misclassified signals |
| `docs/status-report-2026-06-02.md` | Status report Anna brought to her supervisor meeting |
| `docs/system-tech-comparison.md` | Layer-by-layer audit of System A vs B; informed several v0.4.2x recommendations |

### Code (must-know for development)

| File | What it is |
|---|---|
| `systems/masfactory/masfactory_system/graph.py` | The 7-agent graph wiring; per-actor Loop pattern; critic-chain mode selection |
| `systems/masfactory/masfactory_system/classification/schema.yaml` | The four-signal coding scheme as machine-readable YAML — single source of truth |
| `systems/masfactory/masfactory_system/agents/persistence.py` | Where validation + dedup + sentiment + embedding all converge before Supabase insert |
| `systems/masfactory/masfactory_system/agents/reranker_prefilter.py` | v0.4.23 bge-reranker pre-filter (off by default) |
| `systems/masfactory/masfactory_system/structured_output.py` | v0.4.22 `instructor`-based validation at the Classifier → Persistence boundary |
| `systems/masfactory/masfactory_system/sentiment.py` | v0.4.24 VADER-based sentiment scoring |
| `systems/masfactory/masfactory_system/observability.py` | v0.4.25 Phoenix tracing hook (opt-in) |
| `systems/hermes/skills/collect-swiss-quantum-signals/SKILL.md` | The methodology prompt that turns Hermes into a Swiss-quantum signal collector |
| `systems/hermes/scripts/collect_all_actors.sh` | Cron entrypoint — loops actors, calls hermes, calls persister |
| `systems/hermes/scripts/persist_signals.py` | Parses agent JSON output, validates, upserts to Supabase |
| `systems/api/api_app/main.py` | All FastAPI routes (/api/meta, /signals, /scores, /coverage, /compare, …) |
| `systems/api/api_app/coverage.py` | v0.4.21 per-actor coverage metric for §3.5 |
| `systems/reports/reports_system/daily.py` | Daily report generator (one per system per day) |
| `systems/reports/prompts/daily.md` | The LLM prompt template the daily report fills in |
| `systems/web/src/app/*/page.tsx` | 11 Next.js pages: Overview, Signalling, Leaderboard, Ecosystem, Graph, Actors, Compare, Signals, Coverage, Reports, Methodology |
| `data/raw/actors.yaml` | The 40-actor universe — fixed for the evaluation window |
| `docker-compose.yml` | 7-service stack definition |
| `.env.example` | Documented env vars per service |

### Thesis source (the deliverable)

| File | What it is |
|---|---|
| `/Users/annageiser/Library/CloudStorage/OneDrive-FHNW/01 Studium/Bachelor Thesis/Bachelor Thesis - Anna Geiser/Bachelor_Thesis_Geiser_Anna.docx` | The thesis itself — ~11,193 words, all chapters drafted |
| `…/Disposition_BT_Anna_Geiser.docx` | The thesis proposal (Disposition) |
| `…/KickOff_Protocol_BT_Anna_Geiser.docx` | Kickoff meeting protocol with supervisor |
| `…/Notes.docx` | Anna's free-form thesis notes |
| `…/Bachelor Thesis - Anna Geiser/Bachelor_Thesis_Geiser_Anna.md` | markitdown-converted plain-text version of the .docx for grep / diff |

---

## Deployment and operations

### Daily cron schedule (host-level, `/etc/cron.d/...`)

```
04:00 Europe/Zurich   masfactory scrape → reports daily --system masfactory
05:00 Europe/Zurich   hermes scrape    → reports daily --system hermes
Sunday 08:00          weekly reports (System A, System B, thesis-progress)
```

Chain operator between scrape and daily-report is `;` not `&&` (v0.4.26)
— the report fires even on scrape failure so /reports has an entry for
every day.

### Standard deploy flow (after main is in sync)

```bash
ssh root@187.127.87.208
cd /opt/mas-deeptech-research
git pull
docker compose build masfactory hermes api web reports
docker compose up -d
```

If `main` is behind the working branch (today's branch is
`claude/exciting-beaver-11a6e4`), use the surgical pull:

```bash
git fetch origin
git checkout origin/claude/exciting-beaver-11a6e4 -- <changed-files-or-paths>
```

### Model selection (.env on VPS)

Current production line:

```
HERMES_MODEL=mistralai/mistral-nemo
```

(NOT `:free` — the paid endpoint at $0.02/M input + $0.03/M output ≈
$0.30/month.) Anna deposited $10 to OpenRouter; that covers ~33 months
of System B operation at current volume.

System A's model is read from `MASF_MODEL_MAIN` (default
`nvidia/nemotron-3-super-120b-a12b:free`). System A is unaffected by
the reasoning-wrapper bug because MASFactory's response parser is more
permissive than Hermes's — see §4.1.2 paragraph 4 of the thesis for
the architectural-consequence reading.

### How to debug a failed cron run

```bash
# Per-system stdout/stderr is preserved in the named volume
docker compose run --rm --entrypoint sh hermes -c '
  LATEST=$(ls -t /opt/data/state/runs/ | head -1)
  echo "Latest run: $LATEST"
  ls -la /opt/data/state/runs/$LATEST/
  echo "---"
  # Pick any actor's stdout
  cat /opt/data/state/runs/$LATEST/<some-actor-slug>.stdout.txt
'

# Per-run audit folder for System A
ls -t data/raw/runs/ | head -3
# inside: config.json, plan.json, classifications.json, critique.json,
# signals.json, brief.md, tokens.json, dropped_validation.json, etc.

# Cron logs on the host
tail -200 /var/log/masfactory.log
tail -200 /var/log/hermes.log
tail -200 /var/log/reports.log
```

### How to verify which free models OpenRouter has right now

```bash
curl -s https://openrouter.ai/api/v1/models | python3 -c "
import json, sys
data = json.load(sys.stdin)
for m in data['data']:
    p = m.get('pricing', {})
    if p.get('prompt') in ('0', '0.0') and p.get('completion') in ('0', '0.0'):
        print(m['id'])
"
```

Free-tier availability shifts; check before committing to a new model.

### How to A/B a different model for System B without script changes

Override `HERMES_MODEL` on the CLI (after v0.4.30 wired the env passthrough):

```bash
HERMES_MODEL=anthropic/claude-haiku-4-5 \
  HERMES_LIMIT_ACTORS=1 \
  docker compose run --rm hermes
```

---

## Conventions worth knowing

- **Iteration docs are mandatory**: every shipped change gets a
  `docs/iterations/v0.4.X-<short-name>.md` with the design rationale,
  implementation summary, operator runbook, and threats-to-validity
  touched. This is the working audit trail for design-science
  reproducibility.
- **Smart quotes in the .docx**: when editing the thesis XML, use
  `&#x2019;` for apostrophes, `&#x201C;` / `&#x201D;` for double
  quotes. The skill enforces this.
- **Never edit the TOC**: the .docx has a `Table of Contents` section
  pre-built. Heading insertions update the TOC automatically when
  Word opens the file.
- **Never delete completed backlog items**: mark with `[DONE vX.Y]`
  per Anna's directive. The backlog is a chronological record of
  decisions, not just a TODO list.
- **GitHub Actions CI** runs pytest (5 systems), tsc, and Docker
  build-check for every push. Some pre-existing tests are `xfail`ed
  with reasons; new test failures should be fixed, not xfailed.
- **Author name "Claude" for tracked changes / comments** in the
  thesis docx.

---

## What "done for the day" looks like right now (2026-06-23)

- System A: producing real signals daily, has been since deploy.
- System B: producing real signals after v0.4.36 (Mistral Nemo paid).
  First successful smoke at 12:46 Zurich today; tomorrow's 05:00 cron
  is the first end-to-end production day.
- Thesis docx: ~11,193 words, all five chapters drafted, Abstract +
  Preface still empty, List of Figures/Tables/Abbreviations to be
  populated.
- Backlog: nothing shippable without Anna's input.
- Cost: ~$0.30/month operational expense (Mistral Nemo paid) + $0
  for everything else (free Supabase, OpenRouter free-tier with $10
  deposit, free domain).

### Next worthwhile thing to do

1. **Anna runs the gold-standard hand-coding (#102 C.1)** in ATLAS.ti
   on a subset of actors. This populates §3.5 attribution-accuracy
   numbers with real values.
2. **Once gold set exists, learning loop (#108 E.1) becomes
   actionable** — diagnose which signals each system missed.
3. **Abstract + Preface should be written last**, after Anna has read
   the body end-to-end and decided what stays.
4. **List of Figures / Tables / Abbreviations** populates from §3.5
   once placeholder numbers are filled with real Supabase data.

Submission deadline is 2026-08-07. As of handover (2026-06-23), there
are roughly six weeks left. The technical scaffolding is complete; the
remaining work is empirical (running the gold-set coding + filling in
numbers) and editorial (Abstract, Preface, polish).
