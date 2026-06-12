# Lessons learned

Draft for **Chapter 4.1.4 (Methodological and Technical Limitations)** and **Chapter 5.3 (Future Research Directions)** of the thesis. The constructive-research methodology (Kasanen, Lukka & Siitonen 1993) treats the build-evaluate-refine cycles as a primary source of research findings; this document is the structured record of what those cycles surfaced.

Organised in three layers, deepest first.

---

## 1 — Architectural lessons

These would change my design decisions on a second attempt.

### 1.1 — Cron-in-host beats cron-in-container even for "long-running" agents

Both architectures (MASFactory orchestration; Hermes single-loop) are described in their literature as suited to *long-running* tasks. The pragmatic choice for this thesis was the opposite: each container is a short-lived runner invoked by host-side cron. Reasoning:

- A missed tick leaves no zombie process. A long-running container that dies silently is much harder to diagnose than a cron entry whose absence shows up immediately in `/var/log`.
- The audit folder per run is self-contained and human-readable. With a long-running agent, the unit of audit becomes "the agent's lifetime" — much harder to bound.
- Container restarts (after image rebuild) don't strand in-flight work.

**For a follow-up:** the architecture supports both modes. A telemetry comparison between "20 short-lived runs" vs "1 long-running container observed for 20 hours" would be a clean follow-on study.

### 1.2 — The comparative-validity invariant has more value than it costs

Hard rule from the start: **System A and System B share no Python code beyond the data contract (the Supabase schema).** This forced duplication — both systems vendor their own `collectors.py`, their own `embedding.py`, their own labels normalisation table. The cost is real (~5% extra lines of code; a few small bugs caught only after the second system was running).

But the benefit is that the cross-system comparison can be made without the constant footnote "of course, both systems share utility X." That footnote is the most common methodological objection to cross-architecture MAS comparisons in the literature. Eliminating it cost less than expected.

### 1.3 — Single YAML source of truth for the classification schema

`classification/schema.yaml` is loaded at runtime by:
- The Classifier Agent prompt (System A) and the `register_signal` tool docstring (System B).
- The Critic's dimension-evidence rules (System A).
- The Persistence layer's `normalise_dimension()`.
- The FastAPI `/api/meta` endpoint.
- The website's Methodology + Signalling pages.

When the schema migrated v0.3.0 → v0.4.0, the only file that needed updating was the YAML. The agents picked up the new dimensions on the next cron tick; the website re-rendered automatically. A schema-versioned column in Supabase + a YAML-driven prompt would have been worth doing on day 1 if I had known the schema would change this much.

### 1.4 — Per-actor Loop > single-prompt Extractor

The v0.3.0 Extractor saw all 40 actors' documents in one prompt. Attribution drift (the LLM mis-attributing a signal to the wrong actor) was the single largest contributor to bad signals. Wrapping Extractor / Classifier / Critic in a **per-actor `Loop`** so each iteration sees ONE actor's documents was the highest-impact single change to System A's quality, by a long margin.

This is a generalisable lesson for any agentic pipeline where input items can be grouped by a natural attribution key: do the grouping at the graph level, not in the prompt.

---

## 2 — Production-engineering lessons

These are concrete bugs caught during deployment. Each one cost real time to debug; documenting them is the dissertation's contribution to the operations-side of constructive-research.

### 2.1 — Free-tier LLM APIs lie about success

OpenRouter's free-tier Nemotron occasionally returns a 200 OK with an empty `choices` array. The default OpenAI client raises a confusing `IndexError` deep inside the SDK. Fix: `FailoverLegacyOpenAIModel` wraps the call; on `IndexError` or empty-choices, it transparently falls over to the secondary model.

**Generalisable lesson:** when integrating a free-tier API into a production cron, instrument every weird response shape — not just non-2xx HTTP codes.

### 2.2 — `.gitignore` patterns can silently eat your code

Repo-root `.gitignore` line `lib/` (a cookiecutter Python-template default for build artefacts) silently matched `systems/web/src/lib/` and excluded `api.ts` + `types.ts` from every commit. The bug only surfaced when the Docker image was built from a fresh checkout — local node 22 found the files; Docker node 20 didn't.

**Mitigation now in place:** `.gitignore` no longer has language-specific patterns at the repo root; per-system `.gitignore` files contain language-specific entries. Plus: the web Dockerfile has an explicit `RUN test -f tsconfig.json && test -f src/lib/api.ts || (echo BUILD CONTEXT MISSING && ls -la && exit 1)` so a missing-file bug fails the build instantly, with a clear diagnostic.

### 2.3 — `npm install` vs `npm ci` is the difference between "works on my machine" and "works in production"

The first Docker build of the Next.js container used `npm install` without `package-lock.json` in the build context. Local development on Node 22 resolved one sub-dependency tree; Docker on Node 20 resolved another. The tsconfig `paths` aliasing broke in Docker only.

**Fix:** Dockerfile copies `package-lock.json` and uses `npm ci`. This pins the dependency tree across environments. Cost a half-day of debugging; worth a sentence in the thesis.

### 2.4 — Caddy v2 directive is `redir`, not `redirect`

A one-letter difference. The Caddyfile failed validation; the container restart-looped; the domain was unreachable for ~10 minutes. Fix: read the Caddy v2 docs more carefully. The lesson: **with a TLS-terminating reverse proxy, validate the config before bouncing the container.** `caddy validate /etc/caddy/Caddyfile` would have caught this without taking the domain offline.

### 2.5 — `useSearchParams` in Next.js 14 requires `Suspense`

The `/signals` page client component used `useSearchParams` directly. Next.js 14's prerender step fails on this with a confusing "missing Suspense boundary" error. Fix: wrap the inner component in `<Suspense>`.

**Generalisable lesson:** when a framework's prerender step is new (Next 14 was released months before this thesis started), build the first page that uses every features-likely-to-be-prerender-sensitive feature, deploy it, and read the error logs. Don't wait until you have 11 pages.

### 2.6 — The "200 OK no choices" bug is not unique to OpenRouter

Discovered when an empty-choices response came from a paid-tier model too. Defensive coding around LLM API responses (assume any field can be absent; assume any list can be empty) is good practice regardless of provider.

### 2.7 — `caddy reload` returns success but doesn't apply changes

On 2026-06-11, basic-auth setup on the public site burned 3+ hours of debugging that all traced to a single docker-runtime quirk: `docker compose exec caddy caddy reload --config /etc/caddy/Caddyfile` returned success and logged "config loaded", but the running in-memory config was untouched. Every edit to `caddy/Caddyfile` looked applied; none of them were. Six iteration docs (v0.4.4 → v0.4.16) chased phantom Caddyfile-syntax bugs that didn't exist.

The diagnostic that finally exposed it was Caddy's admin-API log line `"config is unchanged"` printed on every reload — a benign-looking message that actually means "the parser produced JSON identical to what I already had", which in our case was the empty-auth start-time config. Without that log line surfacing, the parser-vs-runtime divergence is **invisible**.

**Fix:** always use `docker compose restart caddy` after editing `caddy/Caddyfile`. Never use `caddy reload`. Verified with `curl -I` returning 401 immediately after `restart` but 200 after `reload`.

**Generalisable lesson:** when a config-reload mechanism reports success silently, prove it actually applied changes by observing a behavioural difference — not by reading the reload's exit code. In our case the proof would have been `curl -I` returning 401, not `caddy reload` returning 0. Reload-vs-restart semantics in containerised reverse proxies are an unmarked footgun.

### 2.8 — `:free` LLM models still pre-authorise credit holds

Hermes Phase B's first surfaced failure (after v0.4.5's config wiring) was OpenRouter 402: "requested up to 128000 tokens, but can only afford 110819." The model in question was `nvidia/nemotron-nano-9b-v2:free` — supposed to be unconditionally free. But OpenRouter pre-authorises a credit hold equal to `max_tokens × per-token-rate` for every request, even free ones, and a near-empty balance can fail the pre-auth even though no actual charge will land.

The further twist (v0.4.9) was that v0.4.5–v0.4.8's config-side fixes (cap max_tokens, pin auxiliary models to `:free`, etc.) were all silently overwritten on every container start by the upstream's default config — which routed to a *paid* Claude Opus 4.6. We were debugging a free-tier credit-hold issue while actually paying for Claude Opus calls. The credits Anna burned in the early days of Hermes Phase B all went to Opus.

**Generalisable lesson:** "the agent is using model X" is a claim you must verify from inside the running process, not from the config file you edited. Print the active model name at startup; surface it in the stderr the agent emits per call.

### 2.9 — Docker BuildKit's COPY-layer cache can lie

On 2026-06-12, the v0.4.20e deploy hit a layer-cache bug twice. After `git pull` updated `systems/hermes/scripts/backfill_embeddings.py` on disk, `docker compose build hermes` showed `CACHED [6/9] COPY scripts/` — and the container ran the *previous* version of the script. The `--system masfactory` flag the new version added wasn't recognised; argparse erred out. A second `git pull` + identical build had the same result: layer "cached", contents stale.

The exact mechanism is unclear (file-mtime preservation across the pull? BuildKit content-address collision? buildx provenance attestation reusing an old manifest?), but the *behaviour* is reproducible: BuildKit's COPY layer cache occasionally fails to invalidate when the source file changes.

**Fix:** the surgical version is `git checkout origin/<branch> -- <single-file>` to grab the file directly from the latest commit (bypasses any pull/timestamp weirdness), then rebuild. The blunt version is `docker compose build --no-cache <service>` (~3-5 min penalty but guaranteed). For one-shot scripts, the bind-mount workaround (`-v /host/path/to/script.py:/tmp/script.py:ro` on `docker compose run`) bypasses the image entirely.

**Generalisable lesson:** Treat "CACHED [X/N] COPY …" as a *claim*, not a proof. The cheapest verification is running the script with a flag that would fail loudly on a stale image (`grep -- '--new-flag' /opt/swiss-quantum/scripts/foo.py` to verify on disk; then a smoke command that uses the flag to verify in image). If the smoke fails after a green build, suspect the cache before suspecting the code.

### 2.10 — VPS branch-state divergence is invisible at the file level

Same 2026-06-12 deploy. The VPS at `/opt/mas-deeptech-research/` was on `main`; all my work was on `claude/exciting-beaver-11a6e4`. `git pull` fetched the remote-tracking branch and reported "Already up to date." for the local branch (which it was, vs. `origin/main`). The fetch line `claude/exciting-beaver-11a6e4 -> origin/claude/exciting-beaver-11a6e4` mentioned the branch — but ten lines above the "Already up to date." footer, easy to miss when you're skim-reading a deploy log. Result: the file on disk stayed at the wrong version after a green-looking `git pull`.

**Fix:** for VPS deploys that don't want to switch branches, use `git fetch origin && git checkout origin/<feature-branch> -- <paths>` to surgically pull files. For deploys that should track a branch, run `git branch --show-current` as the first command of every deploy script — it's a single shell command that makes the branch state impossible to miss.

**Generalisable lesson:** "I pulled the latest" is only true if both (a) the fetch updated the remote-tracking branch you wanted, AND (b) the local branch you're on tracks that branch AND fast-forwarded to it. Either half can silently break. The diagnostic is `git status -uno` immediately after pull — if it says "Your branch is up to date with 'origin/<branch>'" and `<branch>` isn't the one you expected, you have divergence.

### 2.11 — Adding a key to a framework edge requires emitting it from the upstream node

On 2026-06-12, the v0.4.23 reranker pre-filter shipped with the loopback edge from `accumulate-actor` declaring `dropped_reranker` as a key it carries — but `AccumulateActor`'s forward function never put `dropped_reranker` in its return dict. The mismatch is a build-time-invisible defect: `python -m masfactory_system.runner build-check` constructs the graph without executing it, so the edge's key-presence check (which happens during `node._message_dispatch_out`) never runs. The first actor loop iteration on the first cron tick crashed with `KeyError: "Missing keys ['dropped_reranker']"`. The defect would have been *silent* until the v0.4.25 Phoenix smoke surfaced it 22 hours after merge.

**Fix:** AccumulateActor was patched to `dropped_reranker: list(attrs.get("dropped_reranker") or [])` so the key is always emitted (empty when disabled, populated when MASF_RERANKER=1). The actual architectural fix would be to extend `build-check` so it executes one synthetic iteration per loop body — enough to trip every edge.

**Generalisable lesson:** Static graph validation (does the graph compile?) and dynamic execution validation (do edges receive the keys they declare?) are different checks. A framework that only does the static one will accept partially-wired changes. If your build-check passes but your first cron tick crashes, the build-check is the gap. Either tighten it, or treat every edge-key addition as requiring a hand-run smoke before it lands.

---

## 3 — Methodological lessons

These changed how I'd frame a similar thesis.

### 3.1 — Pre-registration of evaluation metrics is cheap insurance

Writing [`docs/pre-registration.md`](pre-registration.md) before looking at the live evaluation numbers took ~2 hours. It locks in falsification thresholds so post-hoc adjustments are visible. For a BSc thesis with no formal external statistical review, this is the strongest available mitigation against the designer-equals-evaluator confound (§5.2 of [`threats-to-validity.md`](threats-to-validity.md)).

**Lesson for future students:** ask your supervisor at the first triweekly meeting whether they would countersign a pre-registration document. It costs them nothing to read, signals methodological seriousness, and is cited approvingly by examiners.

### 3.2 — A "second system that does the same thing" is more rigorous than ablations

The thesis builds two complete MAS systems and compares them. Ablation studies (turn off one feature, measure delta) are cheaper but tend to under-explore the *architectural* space — they only sample within one architecture's neighbourhood. A two-architecture comparison samples across architectural categories, even if each architecture is only one point within its category.

The optional-capability-layer A/B is the ablation cheap-and-secondary layer on top of the architectural primary comparison. Having both is what makes the empirical chapter substantive.

### 3.3 — The schema is the thesis

Half the technical work was building two MAS systems. The other half was building, citing, and migrating the v0.4.0 signal classification schema aligned with Ehrenthal et al. (2026). In retrospect, the schema is the more durable contribution: a future researcher can replace either MAS, but the schema YAML — with per-dimension grounding citations — is what they'd cite from this thesis.

For a future student working with a supervisor who is also an author of central source material: **build the schema first, lock it with the supervisor's approval, then build the systems against it.** I went the other way (built v0.3.0, ran on it for a month, then read the Ehrenthal paper carefully and rebuilt as v0.4.0). The migration was clean (deterministic SQL block; zero data loss) but the month of v0.3.0 data is harder to compare with the v0.4.0 future.

### 3.4 — Free-tier infrastructure is a finding, not just a constraint

The entire build runs on Hostinger ($5/month VPS) + Supabase (free tier) + OpenRouter free-tier LLM. Total monthly OpEx ≈ $5. For a thesis on *"cost-effective deep-tech market research,"* this is itself a substantive contribution: the *practical* lower-bound for sophisticated MAS-based market research is much lower than a casual reader of the literature would estimate. Worth a paragraph in the conclusion.

### 3.5 — Audit folders > log lines

Every run writes a self-contained folder under `data/raw/runs/<CET-iso>__<system>/` with: config snapshot, raw documents, per-stage JSON, brief, token tally, dropped signals, embedding summary, dedup log. When a wrong signal is spotted on the website, the folder containing the run that produced it can be opened directly and inspected end-to-end.

Compared with the alternative (per-line structured logs in CloudWatch / Loki / etc.), the audit-folder approach is much easier to reason about in a single-developer thesis context. The cost is disk space (~5 MB per run); the benefit is that a 3-month-old run is debuggable without any infrastructure beyond `ls`.

---

## How to use this document in the thesis

- Section 4.1.4 (Methodological and Technical Limitations) can cite §2 (production lessons) verbatim as "implementation surprises that calibrate the cost side of the cost / quality trade-off."
- Section 5.1 (Summary of Core Insights) draws from §1 (architectural lessons).
- Section 5.3 (Future Research Directions) is built around the "for a follow-up" / "for a future student" hooks in §1 and §3.

Each numbered lesson is paragraph-sized prose ready to drop in. Edit pass before submission: remove first-person ("I"), tighten "generalisable lesson" formulations to fit thesis voice.
