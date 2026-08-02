# Architecture analysis

Audit of the repository as it stands at commit `c0a9ea8` on branch `main`, performed on 2026-08-02. Every claim below was derived by reading source, build configuration, or CI definitions, or by executing the repository's own tooling. Existing Markdown documentation was treated as unverified claim material; the discrepancies found are catalogued in section 6.

## 1. Inventory

### 1.1 Scale

`git ls-files` returns 285 entries. One of these, `systems/hermes/upstream`, is a gitlink rather than a file, so the repository holds 284 files. Total on-disk size of the tracked files, excluding the submodule working tree, is 2.4 MB. The submodule's checked-out working tree occupies a further 116 MB but contributes no tracked content to this repository.

| Extension | Files | Lines |
|---|---|---|
| `.py` | 133 | 21569 |
| `.md` | 66 | 8781 |
| `.tsx` | 27 | 4308 |
| `.yaml` | 5 | 993 |
| `.ts` | 5 | 671 |
| `.sql` | 2 | 648 |
| `.yml` | 3 | 494 |
| `.sh` | 4 | 487 |
| `.json` | 4 | 955 |
| `.toml` | 6 | 204 |
| `.css` | 1 | 274 |
| `.png` | 3 | binary |

Top-level distribution by disk size: `systems` 1732 KB, `docs` 596 KB, everything else under 20 KB each.

### 1.2 Dependency manifests

Six Python `pyproject.toml` files and one `package.json`. Command run:

```
cat systems/*/pyproject.toml
```

No Python lockfile exists anywhere in the tree. Verified by:

```
git ls-files | grep -Ei 'uv\.lock|poetry\.lock|Pipfile\.lock|requirements.*\.txt|pdm\.lock|pixi\.lock'
```

which returns nothing. `.gitignore` lines 100 through 128 discuss `uv.lock`, `poetry.lock`, `pdm.lock` and `pixi.lock` in commented-out form, so no tool ever produced one. Consequently the only exact resolved versions available anywhere in the repository are those in `systems/web/package-lock.json` (lockfileVersion 3), where all nine direct dependencies resolve to exactly their declared pins.

One Python dependency is version-exact by declaration rather than by lockfile: `masfactory==1.0.3` at `systems/masfactory/pyproject.toml:8`. Every other Python dependency is a lower bound.

### 1.3 Build, container, and CI configuration

| File | Purpose |
|---|---|
| `docker-compose.yml` | Eight service definitions, one of which (`phoenix`) is behind the `observability` profile, plus one fully commented-out service (`dashboard`, lines 268 through 284). Four named volumes. |
| `systems/masfactory/Dockerfile` | `python:3.11-slim`, installs the package, runs `masfactory_system.runner build-check` at line 33 as a build gate. |
| `systems/hermes/Dockerfile` | Starts from the digest-pinned upstream agent image at line 28. Installs `ddgs`, `fastembed`, `vaderSentiment`, `selectolax` into the upstream venv. Copies the localextract plugin into the resolved bundled-plugins directory and asserts it imports (lines 74 through 87). Applies `patch_web_tools_backend.py` and asserts the shim (lines 89 through 97). |
| `systems/reports/Dockerfile` | Installs git, marks `/repo` a safe directory, runs `reports_system.runner build-check` at line 39. |
| `systems/api/Dockerfile` | Build context is the repository root so it can copy `classification/schema.yaml` from the masfactory package. Runs `api_app.selfcheck` at line 30. Declares a `HEALTHCHECK` against `/api/health`. |
| `systems/dashboard/Dockerfile` | Streamlit image. Not referenced by any active compose service or CI job. |
| `systems/web/Dockerfile` | Three-stage node 20 build producing a Next.js standalone runtime. Declares a `HEALTHCHECK` against the root path. |
| `caddy/Caddyfile` | Two site blocks: the apex behind basic auth with `/api/*` and catch-all handlers, and a `www` redirect. |
| `searxng/settings.yml` | 70 lines. Limiter disabled, JSON output format enabled, secret is a placeholder. |
| `.github/workflows/ci.yml` | Three jobs described in section 5. |

Five `.dockerignore` files exist. Three of them (`masfactory`, `reports`, `dashboard`) are byte-identical.

### 1.4 Entry points

Enumerated by reading `[project.scripts]` tables, `if __name__ == "__main__"` blocks, Dockerfile `CMD` and `ENTRYPOINT` directives, the crontab samples, and `package.json` scripts.

| Kind | Entry point |
|---|---|
| Console script | `masfactory-run`, `reports-run`, `eval-run` |
| Python module main | `masfactory_system.runner`, `masfactory_system.scripts.sync_manual_signals`, `reports_system.runner`, `reports_system.industry_news_runner`, `eval_app.runner`, `eval_app.qda` |
| Standalone script main | `systems/hermes/scripts/persist_signals.py`, `backfill_embeddings.py`, `backfill_sentiment.py`, `training_context_preflight.py` |
| Container entrypoint | `systems/masfactory/entrypoint.sh`, `systems/reports/entrypoint.sh` |
| Container CMD | `collect_all_actors.sh` (hermes), `uvicorn api_app.main:app` (api), `node server.js` (web), `streamlit run dashboard_app/Home.py` (dashboard, unreachable) |
| Container init hook | `scripts/seed-hermes-home.sh` installed as `/etc/cont-init.d/03-seed-swiss-quantum` |
| Server bootstrap | `api_app.main:app` (FastAPI ASGI app object) |
| Scheduled job | Three `crontab.sample` files, installed by hand into `/etc/cron.d` |
| Test runner | `pytest` per package, configured by `[tool.pytest.ini_options] testpaths = ["tests"]` in each `pyproject.toml` |
| Package script | `next dev`, `next build`, `next start`, `next lint` |
| Build-time check | `masfactory_system.runner build-check`, `reports_system.runner build-check`, `api_app.selfcheck`, the two hermes assertion lines, the web build-context test |

No serverless handler exists.

### 1.5 Ignore-file review

`.gitignore` is 230 lines, mostly the GitHub Python template. Project-specific additions:

- `.hermes/`, `.codebase-memory/*` with a negated exception for `graph.db.zst`
- `.mcp.json` at line 222
- `docs/agent_context`, `docs/thesis_context`, `thesis_context/`
- A negated re-include for `!systems/web/src/lib/` at line 229, added because the template's unanchored `lib/` rule would otherwise swallow the Next.js library directory

One violation: `.mcp.json` is matched by the rule at `.gitignore:222` yet is tracked. Confirmed with `git check-ignore -v --no-index .mcp.json`, which reports `.gitignore:222`.

Nothing else that the ignore files exclude is committed. A scan for AWS keys, GitHub tokens, OpenAI-style keys, and JWT prefixes across every tracked file returned nothing:

```
git ls-files | grep -v '^systems/hermes/upstream$' | xargs rg -n -e 'sk-[A-Za-z0-9]{20,}' -e 'eyJ[A-Za-z0-9_-]{20,}\.' -e 'AKIA[0-9A-Z]{16}' -e 'ghp_[A-Za-z0-9]{30,}'
```

Ignored-but-present-on-disk artefacts that are correctly excluded: `systems/api/build/`, `systems/api/api_app.egg-info/`, `systems/web/.next/`, `systems/web/node_modules/`, eleven `.DS_Store` files, and several `__pycache__` and `.pytest_cache` directories.

### 1.6 Git history

214 commits. First commit 2026-04-21, most recent 2026-07-24. A single author, `Anna`.

Activity by area, derived from `git log --diff-filter=A --name-only`, shows the tree was built roughly in the order `masfactory`, `reports`, `dashboard`, `api`, `web`, `hermes`, `evaluation`. The dormant region is `systems/dashboard`: its last functional change predates the `web` and `api` cutover described in the compose comments, and the compose service was commented out rather than deleted.

The most recent five feature commits all touch `systems/web` and `systems/api`, which is where development is currently active.

### 1.7 Test execution

All suites were executed rather than reasoned about. Environment: Python 3.11.15 in per-package `uv` virtual environments, matching the CI matrix's Python 3.11. Node 22.11.0 with the pre-existing `node_modules`.

| Package | Command | Result |
|---|---|---|
| masfactory | `pytest -q` | 185 passed in 25.50s |
| api | `pytest -q` | 34 passed, 3 xfailed in 17.19s |
| hermes | `pytest -q` | 28 passed |
| evaluation | `pytest -q` | 14 passed, 4 warnings in 36.79s |
| reports | `pytest -q` | 12 passed in 4.97s |
| dashboard | `pytest -q` | 7 passed, 2 xfailed in 21.46s |
| web | `npx tsc --noEmit` | exit 0, no diagnostics |

Total 280 passing, 5 expected-failure, 0 failing. The four evaluation warnings originate in scikit-learn, from `cohen_kappa_score` receiving a single shared label in a deliberately degenerate fixture.

No failures to report.

## 2. Module dependency analysis

### 2.1 systems/masfactory

Internal edges extracted with:

```
rg -n '^\s*(from|import)\s+[a-zA-Z_.]+' -g 'systems/masfactory/**/*.py' -o --no-heading | grep -E "masfactory_system|from \.|from \.\."
```

```
runner.py
  -> audit.AuditFolder
  -> config.{ConfigError, load_settings}
  -> graph.build_graph
  -> model.build_main_model
  -> observability.init
  -> persistence.SupabaseStore
  -> schema.Actor

graph.py
  -> agents (12 node templates and 6 helper callables)

agents/__init__.py
  -> planner, retriever, extractor, classifier, critic,
    critic_consensus, critic_debate, survivor, analyst,
    persistence, reranker_prefilter, loop_nodes

agents/retriever.py
  -> collection (7 collector functions)
  -> schema.{Actor, Document}
  -> training_layer.{load_training_layer, mark_source_fetched}

agents/persistence.py
  -> classification, defense_keywords, embedding,
    persistence (package), sentiment, structured_output

agents/classifier.py     -> classification
agents/critic_consensus.py -> critic
agents/reranker_prefilter.py -> reranker, package root

collection/__init__.py   -> arxiv, news, patents, press, rss, website, websearch
collection/*.py          -> schema

structured_output.py     -> classification, schema
model.py                 -> config
persistence/supabase_client.py -> config
```

Depth from the entry point is at most four hops (`runner` to `graph` to `agents` to `collection` to `schema`). No cycle exists: `agents` never imports `graph`, and `collection` never imports `agents`.

Third-party edges worth noting because they are lazily imported inside functions rather than at module scope, which is how the optional layers degrade to no-ops: `fastembed` at `embedding.py:73` and `reranker.py:77`, `vaderSentiment` at `sentiment.py:58`, `instructor` and `openai` at `structured_output.py:96` and `:127`, `phoenix.otel` and `openinference` at `observability.py:105` and `:114`.

### 2.2 systems/hermes

There is no Python package. `pyproject.toml` declares `py-modules = []` with an inline comment stating that installation exists only so CI can pull dependencies. The dependency structure is therefore process-level rather than import-level:

```
collect_all_actors.sh
  -> python3 (inline heredoc)     parses actors.yaml into actors.tsv
  -> training_context_preflight.py --log-dir --actors-tsv
  -> persist_signals.py --create-run
  -> hermes chat -q                (upstream binary, per actor)
  -> persist_signals.py --actor-slug --stdin-file --run-id
  -> persist_signals.py --close-run

training_context_preflight.py
  -> training_layer.py             (sibling module import)

plugins/web/localextract/provider.py
  -> agent.web_search_provider.WebSearchProvider   (upstream)
  -> plugins.web.localextract._html
```

`_html.py` is deliberately free of upstream imports so it can be unit-tested without the agent package present. `pyproject.toml` sets `pythonpath = ["scripts", "plugins/web/localextract"]` to make both importable in the lightweight CI environment.

The provider is not discovered by ordinary import. It reaches the runtime through two build-time mechanisms, both in the Dockerfile: a copy into the directory resolved by reimplementing `hermes_cli.plugins.get_bundled_plugins_dir`, and a monkeypatch appended to `tools.web_tools` because upstream's `_is_backend_available` hardcodes backend names. Static analysis cannot see either; both are asserted at build time precisely for that reason.

### 2.3 systems/api

```
main.py
  -> data_access, labels, reports, training
  -> config.load_settings
  -> coverage.coverage_payload
  -> insights.insights_payload
  -> knowledge_graph.build_graph_json
  -> meta.meta_payload
  -> scoring.{actor_impact_table, attach_actor_metadata, ecosystem_summary}

scoring.py         -> labels
meta.py            -> labels, config
knowledge_graph.py -> kg_model
data_access.py     -> config
```

`labels.py` is a leaf and is the single source of the dimension weight, cost, and label maps within this package. No cycle.

`data_access.py` imports `supabase` inside a `try` block and sets `Client = None` on `ImportError`, which is what lets the module import in a Supabase-less environment. That guard was added in commit `ab1fc06`.

### 2.4 systems/reports

```
runner.py -> config; then lazily -> daily, weekly_system, weekly_thesis, prompt_loader
daily.py            -> config, openrouter, output_writer, prompt_loader, supabase_reader
weekly_system.py    -> same set
weekly_thesis.py    -> same set plus git_history
industry_news_runner.py -> nothing internal (self-contained by design)
```

The lazy imports inside each `cmd_*` function keep `build-check` runnable without the heavier modules being importable. No cycle.

`industry_news_runner.py` re-implements the RSS fetch that `masfactory_system/collection/rss.py` already provides. Its docstring states the reason: the reports container does not install the masfactory package, so a shared import would create a cross-system dependency.

### 2.5 systems/evaluation

```
runner.py -> data_access, config, metrics (4 functions), report
metrics/__init__.py -> classification_quality, inter_system_agreement, reproducibility, token_efficiency
qda/__main__.py -> qda/cli.py -> codebook, exporter, importer, kappa, refi_qda
```

Two independent trees under one package, joined only by `config` and `data_access`. No cycle.

### 2.6 systems/web

```
src/app/**/page.tsx -> src/lib/api.ts -> src/lib/types.ts
src/app/**/page.tsx -> src/components/{ui,charts,Filters,Markdown,GraphCanvas,ThemeToggle}
src/app/layout.tsx  -> src/components/{Nav,ThemeToggle}
src/app/personas/** -> src/lib/personas.ts -> src/lib/types.ts
src/components/**   -> src/lib/glossary.ts
```

Server components call `api.*`, which targets `API_INTERNAL_URL`. Five pages are client components that fetch relative `/api/*` from the browser: `reports`, `sources`, `signals`, `labels`, `quantum-news`. Those relative calls are resolved by the Next.js rewrite in `next.config.mjs` when the server proxies, and by Caddy when the browser calls directly.

### 2.7 Cross-package dependency

There is exactly one deliberate code-sharing prohibition, stated at `systems/hermes/Dockerfile:20-23`: System A and System B must share no Python code beyond the Supabase schema. The audit confirms it holds. The cost is three vendored duplications:

| Duplication | Files | Relationship |
|---|---|---|
| Training layer | `masfactory_system/training_layer.py`, `hermes/scripts/training_layer.py` | Byte-identical, SHA-256 `8fed7f26...` |
| Label and taxonomy maps | `api_app/labels.py` (394 lines), `dashboard_app/labels.py` (340 lines) | Divergent copies of the same concept |
| Scoring | `api_app/scoring.py` (109 lines), `dashboard_app/scoring.py` (167 lines) | `api_app/scoring.py:2` states it is a vendored copy of the dashboard version |
| RSS fetching | `masfactory_system/collection/rss.py`, `reports_system/industry_news_runner.py` | Re-implementation, documented at `industry_news_runner.py:11-15` |
| Full-text extraction | `masfactory_system/collection/website.py::_visible_text`, `localextract/_html.py` | Deliberate separate implementation of an identical method, documented at `provider.py:21-29` |

Only the first is byte-identical and therefore mechanically checkable for drift. The others can drift silently. No test compares any pair.

## 3. Runtime paths

### 3.1 System A collection

Entry: `python -m masfactory_system.runner run-once`, reached through `entrypoint.sh` from `docker compose run --rm masfactory run-once`.

1. `load_settings(require_supabase=True)` raises `ConfigError` on missing `OPENROUTER_API_KEY`, `SUPABASE_URL`, or `SUPABASE_SERVICE_KEY`; `main()` catches it and returns exit code 3 (`runner.py:252-256`).
2. Actors are read from `--actors-file` or `/data/raw/actors.yaml` and validated into `Actor` models.
3. `SupabaseStore.upsert_actors` writes the roster.
4. An `AuditFolder` is created under `MASF_AUDIT_DIR`; `config.json` and `actor_pool.json` are written. The settings snapshot redacts `openrouter_api_key` and `supabase_service_key`, replacing each with a length marker (`runner.py:38-44`).
5. `start_run` opens the `runs` row and returns its UUID.
6. `init_phoenix(run_id)` runs before the model is constructed so the OpenAI SDK is instrumented before its first call. Returns `False` and writes nothing when `PHOENIX_ENABLED` is unset.
7. `build_main_model(settings)` builds the failover-wrapped OpenRouter model.
8. `template_defaults_for(type_filter=Agent, model=model)` binds one shared model instance to every Agent node, which is why a single token tracker holds the run total.
9. `build_graph().build().invoke(...)` executes: Planner, Retriever, the per-actor Loop, Analyst, Persistence.
10. On any exception the traceback is printed, `error.txt` is written to the audit folder, `finish_run(status="error")` is called, and the exit code is 1.
11. Token usage is read off the model's `_token_tracker`, and off `model.fallback._token_tracker` when the failover wrapper switched. Recording is wrapped so that a failure here cannot fail an otherwise-complete run (`runner.py:161-162`).
12. `finish_run(status="ok")`, then a one-line summary to stdout.

The Loop is bounded at `max_iterations=500` (`graph.py:211`) and terminates on `actor_loop_done`.

The Critic section of the Loop has three wirings selected at import time by `_build_critic_chain()` (`graph.py:112-170`). Because selection happens when `graph.py` is imported, changing `MASF_CRITIC_CONSENSUS_PASSES` requires a new process, not merely a new invocation.

### 3.2 System B collection

Entry: the container CMD `collect_all_actors.sh`.

1. `COLUMNS=10000` is exported so the upstream Rich formatter does not hard-wrap JSON string values (line 42).
2. Three environment variables are checked; a missing one exits 2. A missing actors file exits 3.
3. Run directories older than 30 days under `$HERMES_HOME/state/runs` are pruned.
4. An inline Python heredoc converts `actors.yaml` into a five-column TSV. Fields are extracted downstream with `cut -f` rather than `read`, because `read` with a tab IFS collapses consecutive empty fields (documented at lines 150 through 159).
5. `training_context_preflight.py` writes per-actor context blocks; failures are swallowed with `|| true`.
6. `persist_signals.py --create-run` returns the run UUID. A shell trap closes the run as `error` on any unexpected exit.
7. Per actor: build the prompt, run `timeout 600 hermes chat` with `--skills collect-swiss-quantum-signals,arxiv,blogwatcher --toolsets web,skills`, capture stdout and stderr to per-actor files, then pipe stdout to the persister.
8. If the primary model errored or produced zero signals, the actor is retried once with `HERMES_MODEL_FALLBACK`. The model that produced the accepted output is recorded.
9. The run is closed `ok` when every actor succeeded, `error` otherwise, with a message pointing at the per-actor stderr files.

The reasoning-token defence is three-layer and the layers are individually verifiable: layer 1 is `agent.reasoning_effort: "none"` in `cli-config.yaml:181`; layer 2 is the `_strip_reasoning_artefacts` pass in `persist_signals.py`, covered by `tests/test_reasoning_strip.py`; layer 3 is the fallback retry above. `cli-config.yaml:45-51` records that the previously used `model.reasoning.*` key is ignored by this CLI and has been removed.

### 3.3 Browser read path

`GET https://mas-deeptech-research.cloud/leaderboard`

1. Caddy terminates TLS and applies basic auth to the whole site.
2. The catch-all `handle` block proxies to `web-container-g:3000`.
3. The Next.js server component calls `api.scores()`, which issues `GET ${API_INTERNAL_URL}/api/scores` with `cache: "no-store"`. Without `no-store` the pages would be statically prerendered at build time and frozen (`api.ts:23-25`).
4. FastAPI's `get_scores` calls `_scored`, which calls `da.signals` and `da.actors`.
5. `data_access` checks its in-process TTL cache, default 60 seconds, before hitting Supabase.
6. `actor_impact_table` computes the six metrics; `attach_actor_metadata` left-joins actor names and categories.
7. `_records` converts the DataFrame to JSON-safe dicts, mapping NaN and infinity to null.

Browser-initiated calls to `/api/*` from the five client pages take a different route: Caddy's `handle /api/*` block sends them straight to the API container, bypassing Next.js.

### 3.4 Report generation

`reports_system.runner daily --system masfactory` loads settings, fetches signals, runs, and token rows for the window, renders the prompt from `prompts/daily.md`, calls OpenRouter, and writes a dated Markdown file under `RPT_REPORTS_DIR`. The weekly-thesis variant additionally shells out to `git log` inside the read-only `/repo` bind mount; `systems/reports/Dockerfile:34` whitelists that path as a git safe directory because the container runs as root against a host-owned checkout.

Both cron chains join the report step to the scrape step with `;` rather than `&&`. The crontab comments state the reason: a scrape failure previously swallowed the report and left gaps on the reports page.

## 4. Cross-cutting concerns

| Concern | Implementation | Evidence |
|---|---|---|
| Authentication | HTTP basic auth at the proxy only. No application-level auth anywhere. | `caddy/Caddyfile:30-37` |
| Authorisation | None. Every authenticated visitor can call the six mutating API routes. | `api_app/main.py` has no dependency-injected auth |
| CORS | `allow_origins` from `API_CORS_ORIGINS` (default `*`), `allow_methods=["GET"]`, `allow_credentials=False`. The `GET`-only method list means the POST, PATCH and DELETE routes are same-origin only. | `main.py:38-44` |
| Input validation | Pydantic models at the API boundary (`training.py` field validators) and at the classifier-to-persistence boundary (`structured_output.py`). FastAPI `Query` constraints bound every numeric parameter. Database `CHECK` constraints on `runs.system`, `signals.system`, `signals.source_kind`, `signals.confidence`, `signal_flags.reason`, `signal_sources.kind`, `signal_source_runs.status`. | `main.py:109-119`, `schema.sql` |
| Error handling, producers | Each collector is wrapped in its own `try` and appends to `retriever_errors` rather than raising (`retriever.py:102-173`). The whole graph invocation is wrapped so failure still closes the run row. Token recording has its own guard. | `runner.py:89-162` |
| Error handling, System B | Per-actor failures are counted, not raised. A shell trap guarantees the run row is closed. | `collect_all_actors.sh:137-147` |
| Error handling, frontend | `src/app/error.tsx` and `src/app/not-found.tsx` are the Next.js convention boundaries. | 13 and 10 lines respectively |
| Retry | `tenacity` is a declared dependency of masfactory and reports. `collect_all_actors.sh` retries once per actor with the fallback model. `model.py` wraps the primary model in a failover that switches to the fallback on OpenRouter no-choices errors. | `pyproject.toml`, `runner.py:148-153` |
| Caching | 60-second in-process TTL cache in `api_app/data_access.py`. `lru_cache` on `meta.schema()`. A web-page cache under `MASF_WEB_CACHE_DIR` used by `collection/website.py`. Threading locks guard the lazily loaded embedding, reranker and sentiment models. | `data_access.py`, `meta.py:20`, `graph.py:70` |
| Logging | Python `logging` in `patents.py`, `rss.py`, `reranker.py`, `embedding.py`, `sentiment.py`, `observability.py`, `industry_news_runner.py`, `localextract/provider.py`. Elsewhere plain `print` to stdout, captured by cron redirection into `/var/log/*.log`. No structured logging, no log aggregation. | grep across the tree |
| Tracing | Optional OpenTelemetry through Arize Phoenix, System A only. The compose comment at line 200 states System B is deliberately not instrumented to preserve the comparison invariant. | `observability.py`, `docker-compose.yml:200-232` |
| Auditing | Per-run JSON folder on disk plus a `public.audit_log` table. `audit.py` stamps folder names in `Europe/Zurich`. | `audit.py` |
| Health checks | `HEALTHCHECK` on the api and web images; a `/healthz` healthcheck on searxng gating `depends_on: service_healthy` for both producers. | Dockerfiles, `docker-compose.yml:260-265` |
| Rate limiting | Politeness only: 1 request per second per host in the localextract provider, a threading-guarded delay in `collection/arxiv.py`, robots.txt respect in `collection/website.py` and the provider. No inbound rate limiting. | `provider.py`, `arxiv.py:29-31` |
| Secrets handling | Read from environment only. The settings snapshot written to Supabase redacts the two secret fields. No secret is committed. | `runner.py:38-44` |

## 5. Test strategy

Framework: `pytest` for all six Python packages, configured identically through `[tool.pytest.ini_options]`. No `conftest.py` exists anywhere, and no fixtures are shared across packages.

Type checking: `tsc --noEmit` with `strict: true` for the frontend. No Python type checker is configured; `mypy` and `pyright` appear nowhere in the tree.

Linting: none configured. `next lint` is declared as a script but no ESLint configuration file exists and no CI job runs it.

Test types present:

| Type | Where | Notes |
|---|---|---|
| Unit | All six packages | The overwhelming majority. Pure functions over fixtures. |
| Graph-compilation | `masfactory/tests/test_graph_builds.py` | Compiles the graph in all three Critic modes with a stub model. |
| Contract or shape guard | `masfactory/tests/test_upstream_shape_guard.py` | Asserts the shape the upstream framework hands back, added as a hotfix in v0.4.42. |
| HTTP route | `api/tests/test_api.py` | FastAPI `TestClient` against the app with Supabase stubbed. Three tests are `xfail`. |
| Import smoke | `dashboard/tests/test_dashboard_skeleton.py`, `reports/tests/test_reports_skeleton.py` | Verify modules import and prompts load. Two dashboard tests are `xfail`. |
| Behavioural regression | `reports/tests/test_llm_failure_short_circuit.py` | Encodes the v0.4.43 hotfix. |
| Text-processing | `hermes/tests/test_reasoning_strip.py`, `test_localextract_html.py` | Cover the two load-bearing pure functions of System B's wrapper. |
| Round-trip | `evaluation/tests/test_qda_refi.py` | REFI-QDA export then import then compare. |

Coverage by area, judged by which modules have a corresponding test file:

| Area | Covered |
|---|---|
| masfactory collectors | arxiv, patents, press, websearch have dedicated tests. `news.py`, `rss.py`, `website.py` do not. |
| masfactory agents | critic_consensus, critic_debate, persistence (semantic dedup), loop_nodes (through the shape guard). planner, extractor, classifier, analyst, survivor have none. |
| masfactory optional layers | embedding, reranker, sentiment, structured_output, observability all covered. |
| api | 34 tests plus 3 xfail across routes and the knowledge graph. |
| hermes | The two pure helpers only. Neither `collect_all_actors.sh` nor the persister's Supabase path is exercised. |
| reports | Skeleton plus one regression. The three generators are not directly tested. |
| evaluation | Metrics and the QDA round trip. |
| dashboard | Import smoke only. |
| web | Type checking only. No unit, component, or end-to-end tests, and no test framework is installed. |

No integration test touches Supabase, OpenRouter, SearXNG, or any collector's live endpoint. Every suite runs offline. There is no coverage measurement configured and no coverage threshold in CI.

CI, from `.github/workflows/ci.yml`:

- `python-tests`: a six-way matrix (`masfactory`, `hermes`, `reports`, `api`, `dashboard`, `evaluation`) running `pip install .`, `pip install pytest`, `pytest -q`. `fail-fast: false`.
- `web-typecheck`: `npm ci --no-audit --no-fund --include=dev` then `npx tsc --noEmit`.
- `docker-builds`: a five-way matrix (`masfactory`, `hermes`, `reports`, `api`, `web`) building each image with `push: false` and GitHub Actions layer caching. `dashboard` is absent from this matrix.

Triggers are pushes and pull requests against `main` and `dev`. No job deploys anything.

## 6. Discrepancies between documentation and code

Every row below was checked against source. The documentation column names the file that makes the claim; the code column names the file that contradicts it.

### 6.1 README.md (the version replaced by this audit)

| Claim | Location | Reality |
|---|---|---|
| System A runs daily at 04:00 Europe/Zurich | README line 9 | `systems/masfactory/crontab.sample:25` schedules `0 2 * * *`. The correct time is 02:00. |
| "there are no Python unit tests in `systems/hermes/`" | README lines 74 through 75 | `systems/hermes/tests/` contains two test files, 28 tests, all passing. They were added in v0.4.41 and are a CI matrix entry. |
| "Apache-2.0. See LICENSE." | README line 80 | No `LICENSE` file exists. It was deleted in commit `16d0156`. The link is broken. |
| Layout tree lists six directories under `systems/` | README lines 31 through 37 | Seven exist. `systems/dashboard/` is omitted. |
| Layout tree omits `caddy/`, `searxng/`, `.github/` | README lines 25 through 40 | All three exist and are load-bearing. |
| `data/raw/runs/` shown as a repository directory | README line 29 | Not tracked. Created at runtime inside the bind mount. |
| Local test instructions cover masfactory only | README lines 70 through 76 | Six packages have suites; CI runs all six. |

### 6.2 docs/architecture.md

| Claim | Location | Reality |
|---|---|---|
| Model is `nvidia/nemotron-3-super-120b-a12b:free` with a `llama-3.3-70b` fallback | line 13 | `config.py:20-21` sets `nvidia/nemotron-3-ultra-550b-a55b:free` and `qwen/qwen3-next-80b-a3b-instruct:free`. `cli-config.yaml:29` agrees with the code. |
| "Seven containers" | line 3 and the heading | `docker-compose.yml` defines eight services. `searxng` (added v0.5.0) and `phoenix` are both absent from the count and from the diagram; `dashboard` is counted but is commented out. |
| The dashboard "remains in the compose file as a transitional fallback, reachable on internal :8501" | lines 5, 62 through 64, 133, 219 | `docker-compose.yml:270-284` has the entire service commented out. It is not reachable at all. |
| "11 endpoints" | lines 51 and 130 | 26 route decorators in `api_app/main.py`. |
| "11 public pages" | lines 55 and 131 | 17 `page.tsx` files under `src/app`. |
| Hermes upstream is "v0.16.0" | line 169; also `docker-compose.yml:38` | The image is pinned to tag `v2026.6.5`; the submodule is at `v2026.6.5-457-gba44de06d`. No `v0.16.0` appears anywhere in the build. |
| `signals` is idempotent on `(actor_slug, source_url, content_hash)` | line 190 | The unique key became four columns including `system` in v0.5.0. See `schema.sql:56` and `schema.sql:74-113`. |
| "Five-collector funnel", listing arxiv, website, news, press, patents | lines 221 through 231 | `collection/__init__.py` exports seven collectors. `rss` and `websearch` are missing from the table. |
| Semantic dedup default window is 30 days | line 242 | `agents/persistence.py:49` defaults to 90. The docstring there records the v0.4.0 change from 30. |
| "System B mirrors each of these as a tool in the Tools Registry" | line 233 | Not supported by any source in this repository. System B is restricted to `--toolsets web,skills` (`collect_all_actors.sh:307`). It has generic web search and extract, not five actor-specific collectors. |
| Audit-folder listing includes `plan.json`, `raw_docs/`, `classifications.json`, `critique.json`, `signals.json`, `brief.md` | lines 253 through 269 | Only `config.json`, `actor_pool.json`, `final_attributes.json`, `tokens.json`, and conditionally `phoenix.json`, `error.txt`, `tokens_error.txt` are written by `runner.py`. The remaining names would have to be written by `agents/persistence.py`; this was not fully traced and is listed as an open question. |
| System A "7 conceptual agents plus 3 helper CustomNodes" | line 127 | Five Agent nodes and five CustomNode modules exist. The count depends on whether Survivor and the reranker prefilter are included; the table at lines 152 through 162 omits the reranker prefilter, which is always inserted (`graph.py:140`). |

### 6.3 Other documents

| Claim | Location | Reality |
|---|---|---|
| Deploy instruction for the industry-news populator | `docs/migrations.md:385` | The command is correct and the module exists, but no cron entry runs it. The table it populates therefore only grows when the command is run by hand. |
| `sync_manual_signals.py` runs "nightly and after each manual-signals POST or PATCH" | `api_app/main.py:47-48` | This is a source comment rather than documentation, and it is inaccurate. No crontab sample schedules it and no subprocess call in `api_app` invokes it. |
| `.env.example` documents `HRM_LIMIT_ACTORS`, `HRM_MAX_ITERATIONS`, `HRM_SEMANTIC_DEDUP`, `HRM_SEMANTIC_DEDUP_THRESHOLD`, `HRM_SEMANTIC_DEDUP_DAYS` | `.env.example:131-152` | No file in this repository reads any of them. The System B semantic-dedup capability that `docs/architecture.md:242` describes as available is not implemented on the System B side. |
| `.env.example` documents `GEMINI_API_KEY` and `TELEGRAM_BOT_TOKEN` | `.env.example:190,192` | Neither is read by any file here, and neither is passed through in `docker-compose.yml`. |
| `TAVILY_API_KEY` appears twice in the same file | `.env.example:94` and `:191` | Duplicate key. The second occurrence silently wins when the file is sourced. |
| "The dashboard lives at `https://mas-deeptech-research.cloud/`. Caddy in front of the Streamlit container handles TLS" | `docs/dns-and-dashboard.md:3` | Caddy's catch-all handler proxies to `web-container-g:3000` (`caddy/Caddyfile:43`). The Streamlit service is commented out and has no route. The DNS instructions in the same file remain correct. |

### 6.4 Documents that hold up

The iteration records under `docs/iterations/` were spot-checked against code and were accurate in every case examined. `v0.4.45-hermes-reasoning-disable.md` correctly describes the `reasoning_effort` change visible at `cli-config.yaml:170-181`; `v0.5.1-stage2b-system-b-fulltext.md` correctly describes the provider-plus-shim mechanism visible in the Dockerfile. Weighting these above general prose documentation, as the audit brief directs, was justified by the evidence.

`docs/migrations.md` matches `schema.sql` on every migration examined.

## 7. Assumptions log

Each assumption was recorded during the audit and then either confirmed or discarded.

| Assumption | Outcome | Basis |
|---|---|---|
| The repository is a Python monorepo with one deployable per directory | Confirmed with one exception | Six Python packages plus one Node package; `systems/evaluation` is not deployable and has no Dockerfile. |
| `systems/hermes/upstream` contributes source files to the audit surface | Discarded | It is a gitlink. `git ls-files` shows one entry, not a tree. Excluded from all counts and all searches. |
| A lockfile exists somewhere for Python | Discarded | None found. Exact resolved versions are unobtainable for the Python stack. |
| The Streamlit dashboard is live | Discarded | Compose service commented out; absent from the Docker build CI matrix; no Caddy route. |
| The dashboard is therefore dead code and removable | Discarded as a conclusion | It is still in the pytest CI matrix and still passes, and the compose comment frames removal as a pending decision. Reclassified as Tier B, requiring a maintainer answer. |
| `industry_news_runner.py` is orphaned | Discarded | It is a documented manual entry point with a `__main__` block, referenced in `docs/migrations.md:385`. Unscheduled, not unreachable. |
| `sync_manual_signals.py` is orphaned | Discarded | Same pattern. Documented at `docs/migrations.md:712`. |
| The hermes `scripts/*.py` files not called by `collect_all_actors.sh` are dead | Discarded | `backfill_embeddings.py` and `backfill_sentiment.py` are one-shot maintenance tools with full argparse interfaces, copied into the image by `COPY scripts/`. |
| `SurvivorNode` is dead code | Confirmed as unwired, retained by intent | Exported at `agents/__init__.py:47`, never in the node list. `graph.py:20-23` states the retention is deliberate. |
| The vendored `training_layer.py` pair is accidental duplication | Discarded | It is required by the stated comparison-validity invariant. |
| The two favicon PNGs serve different purposes | Discarded | Byte-identical, SHA-256 `77858d58...`. One is the Next.js file convention, the other is referenced from `layout.tsx`. |
| `systems/masfactory/masfactory_system/persistence/migrations/v0.5.0-per-system-dedup.sql` is applied by code | Discarded | Nothing references it. Its content is duplicated inline in `schema.sql:74-113`, and `[tool.setuptools.package-data]` includes only `persistence/*.sql`, not the `migrations/` subdirectory, so it is not even packaged. |
| Streamlit `pages/*.py` files are unreferenced | Discarded | Streamlit loads them by directory convention. |
| The zero-reference `docs/iterations/*.md` files are stale | Discarded | They are an append-only iteration log, indexed by `docs/iterations/README.md`. Being unreferenced is their normal state. |
| `MASF_WEB_CACHE_DIR` is an environment variable | Discarded | `web_cache_dir` is a graph attribute set from a literal in `runner.py:106`, not from the environment. Removed from the configuration reference. |
| The evaluation `Settings` dataclass is frozen, making `runner.py:52` a latent crash | Discarded | `eval_app/config.py:13` declares `@dataclass` without `frozen=True`. The mutation is legal. |
| `npm run lint` is wired into CI | Discarded | Declared in `package.json` only. No ESLint config, no CI job. |
| CI deploys on merge | Discarded | `push: false` at `ci.yml:126`; no deployment job exists. |

## 8. Items the audit could not verify from the repository alone

The first two entries below were resolved after the fact by read-only inspection of the production host. See section 9.

- **Production state.** Resolved. See section 9.
- **Resolved Python dependency versions in the deployed images.** Resolved. See section 9.4.
- **The full audit-folder file list.** `runner.py` writes five files; `docs/architecture.md` lists thirteen. The remaining eight would be written from `agents/persistence.py` and the Loop nodes. Confirming the exact set requires either executing a real run or a line-by-line read of `agents/persistence.py` and `agents/loop_nodes.py` that this audit did not perform.
- **Whether the two full-text extraction implementations actually agree.** `localextract/_html.py` is documented as a byte-for-byte re-implementation of `collection/website.py::_visible_text`. No test compares their output on the same input. Resolving it requires a differential test, which cannot be written without violating the code-sharing invariant unless the fixtures rather than the code are shared.
- **Runtime behaviour of the upstream Hermes agent.** The submodule is 116 MB of third-party code outside the audit scope. Claims about upstream internals in `docs/architecture.md` were not verified beyond confirming that the named files exist.
- **Whether the three `xfail` tests in the api suite and the two in the dashboard suite mark known defects or intentional gaps.** The markers were observed; their reasons were not read.

## 9. Production verification

Read-only inspection of the deployment host, performed 2026-08-02 over SSH as `root@187.127.87.208` (`srv1684595`, Ubuntu, up 50 days). No file was modified, no service was restarted, no container was created except three throwaway `docker run --rm` invocations of already-built images to read their installed package lists. No secret value is reproduced in this document.

This section resolves the first two items in section 8 and adds seven findings that are not derivable from the repository.

### 9.1 Deployed revision and cron

The deploy directory is `/opt/mas-deeptech-research`, on branch `main` at commit `c0a9ea8`, which is the same commit this audit analysed. Two tracked files carry local modifications, both expected: `caddy/Caddyfile` (2 changed lines) and `searxng/settings.yml` (6 changed lines).

Three cron files are installed under `/etc/cron.d`, and all three fire. Two of them differ from the committed samples.

| Installed file | Matches sample | Difference |
|---|---|---|
| `/etc/cron.d/reports` | Yes | none |
| `/etc/cron.d/mas-deeptech-research-masfactory` | No | Adds a third chained step the sample does not contain: `docker compose run --rm --entrypoint python masfactory -m masfactory_system.scripts.sync_manual_signals >> /var/log/manual_sync.log`. It also redirects the daily-report step to `/var/log/masfactory.log` rather than `/var/log/reports.log`. |
| `/etc/cron.d/mas-deeptech-research-hermes` | No | Joins the scrape and the daily-report step with `&&` where the sample uses `;`. |

The `&&` deviation reverts the v0.4.26 fix in intent. `systems/hermes/crontab.sample:22-27` records that the report step was deliberately changed to `;` so that a failed scrape cannot swallow the daily report. In practice the exposure is narrower than that comment implies, because `collect_all_actors.sh` exits 0 even when individual actors fail; only a fatal preflight failure (exit 2 or 3) or a failed run-row creation (exit 1) would suppress the report. It is still a live divergence between the committed artefact and the running system.

The masfactory deviation is the more consequential one, and in the opposite direction: the production schedule is ahead of the repository. See 9.3.

### 9.2 Secrets, exposure, and the running container set

Both deploy-time substitutions were performed. `caddy/Caddyfile` contains a real bcrypt hash and no longer contains the `PLACEHOLDER_HASH_REPLACE_BEFORE_DEPLOY` string; `searxng/settings.yml` no longer contains `ultrasecretkey`. Verified by presence check only; no value was read or transmitted.

Six containers are running:

| Container | Image | Uptime | Ports |
|---|---|---|---|
| `caddy-container-e` | `caddy:2.10-alpine` | 5 weeks | 80, 443 published |
| `api-container-f` | `mas-deeptech-research/api:0.1.0` | 8 days, healthy | 8000 internal |
| `web-container-g` | `mas-deeptech-research/web:0.1.0` | 8 days, **unhealthy** | 3000 internal |
| `searxng-shared` | digest `sha256:02aa607e...` | 3 weeks, healthy | 8080 internal |
| `dashboard-container-d` | `mas-deeptech-research/dashboard:0.1.0` | 4 weeks | **8501 published on 0.0.0.0** |
| `mas-phoenix` | `arizephoenix/phoenix:latest` | 7 weeks | 6006 bound to 127.0.0.1 |

The searxng digest matches the pin at `docker-compose.yml:247` exactly.

Two of these contradict the repository.

**The Streamlit dashboard is running and publicly reachable without authentication.** `docker-compose.yml:270-284` has the service commented out, so compose no longer manages it; the container predates the comment-out and `restart: unless-stopped` has kept it alive across reboots. Compose confirms this in every cron log line: `Found orphan containers ([dashboard-container-d]) for this project`. Port 8501 is published on `0.0.0.0` and on `[::]`, `ufw` is inactive, and the `iptables` INPUT policy is ACCEPT. `curl http://187.127.87.208:8501/` returns HTTP 200. The authenticated site returns HTTP 401 without credentials, so the dashboard is a complete bypass of the only access control in the system, over plain HTTP, serving the same Supabase data.

**Phoenix is running** despite being behind the `observability` compose profile, though its port is correctly bound to loopback only.

### 9.3 The manual-signal sync has been failing since v0.5.0

`/var/log/manual_sync.log` shows 17 successful propagations followed by 29 consecutive failures, every one of them the same PostgREST error:

```
HTTP 400 {"code":"42P10", "message":"there is no unique or exclusion constraint matching the ON CONFLICT specification"}
```

Root cause, confirmed by reading the three call sites:

| Call site | `on_conflict` specification | Updated for v0.5.0 |
|---|---|---|
| `systems/masfactory/masfactory_system/persistence/supabase_client.py:137` | `actor_slug,source_url,content_hash,system` | Yes |
| `systems/hermes/scripts/persist_signals.py:554` | `actor_slug,source_url,content_hash,system` | Yes |
| `systems/masfactory/masfactory_system/scripts/sync_manual_signals.py:146` | `actor_slug,source_url,content_hash` | **No** |

The v0.5.0 migration dropped the three-column unique constraint and replaced it with a four-column one including `system` (`schema.sql:83-113`). The migration's own operator note at `persistence/migrations/v0.5.0-per-system-dedup.sql:8` names the two call sites that were updated and does not mention the third, so the omission dates from design rather than from deployment.

Effect: since v0.5.0 shipped on 2026-07-09, no curated manual signal has been propagated into `public.signals`. The `/labels` curation workflow still writes to `manual_signals` (19 rows), but the `system='manual'` slice that `VALID_SYSTEMS` at `api_app/main.py:52` expects has been frozen at 16 rows.

**Fixed on `main` after this audit.** The key now comes from a single `SIGNALS_ON_CONFLICT` constant in `sync_manual_signals.py`, and `systems/masfactory/tests/test_signals_on_conflict.py` compares all three writers against the constraint parsed out of `schema.sql`. Verified to fail on the pre-fix code (3 failures naming the offending writer) and pass after. The production container still runs the old image; the backlog of 3 unpropagated manual signals will clear on the first nightly run after `docker compose build masfactory`.

### 9.4 Resolved dependency versions

Read with `pip freeze` inside each production image. These are the versions the deployed system actually runs, and they are recorded here because nothing else in the repository records them.

| Package | Declared constraint | Resolved in production |
|---|---|---|
| masfactory | `==1.0.3` | 1.0.3 |
| supabase | `>=2.7.0` | 2.31.0 |
| pandas | `>=2.2.0` | **3.0.5** |
| openai | `>=1.50.0` | **2.45.0** |
| fastapi | `>=0.115.0` | 0.139.2 |
| starlette | transitive | 1.3.1 |
| uvicorn | `>=0.30.0` | 0.51.0 |
| networkx | `>=3.3` | 3.6.1 |
| pydantic | `>=2.7.0` | 2.13.4 |
| httpx | `>=0.27.0` | 0.28.1 |
| selectolax | `>=0.3.21` | 0.4.10 |
| tenacity | `>=8.2.0` | 9.1.4 |
| feedparser | `>=6.0.11` | 6.0.12 |
| fastembed | `>=0.4.0` | 0.8.0 |
| onnxruntime | transitive | 1.27.0 |
| instructor | `>=1.6.0` | 1.15.4 |
| arize-phoenix-otel | `>=0.6.0` | 0.16.1 |
| openinference-instrumentation-openai | `>=0.1.18` | 0.1.52 |
| vaderSentiment | `>=3.3.2` | 3.3.2 |
| PyYAML | `>=6.0.2` | 6.0.3 |
| urllib3 | `>=2.2.0` | 2.7.0 |
| next | `14.2.15` | 14.2.15 |

Two of these crossed a major version boundary while still satisfying the declared lower bound: `pandas` 2 to 3, and `openai` 1 to 2. Both are load-bearing. This is the unlocked-dependency risk from section 1.2 materialising in production rather than a hypothetical. A rebuild today would resolve different versions again, and nothing records what any past image contained.

### 9.5 The web healthcheck has never passed

`web-container-g` reports `unhealthy` with a failing streak of 24310, which at the 30-second interval declared in `systems/web/Dockerfile:31-32` is the entire 8-day lifetime of the container. Every probe returns:

```
curl: (7) Failed to connect to localhost port 3000 after 0 ms: Couldn't connect to server
```

The service itself is fine. `curl http://web-container-g:3000/` from inside the api container returns HTTP 200, and the public site serves normally behind basic auth. The Next.js standalone server binds an interface that `localhost` inside the container does not resolve to, so the probe is wrong rather than the app. The practical consequence is that the health signal is permanently useless: an actual outage would be indistinguishable from the current state, and any future `depends_on: service_healthy` on `web` would deadlock.

### 9.6 Silent 1000-row truncation on every signal query

This is the most consequential finding of the audit and is not visible from the repository, because it only appears once the table exceeds 1000 rows.

Neither Supabase reader paginates. `api_app/data_access.py:85-99` and `eval_app/data_access.py:51-61` both build a PostgREST query with `.gte(...)` and `.order("inserted_at", desc=True)` and call `.execute()` with no `.range()`. PostgREST on Supabase applies a default `max-rows` of 1000 and returns a partial result without error.

Measured against the live API:

| Requested `limit` | Rows returned |
|---|---|
| 500 | 500 |
| 1500 | 1000 |
| 5000 | 1000 |

`api_app/main.py:118` accepts `limit` up to 5000, so the parameter promises more than the layer beneath it can deliver, silently.

Exact row counts in the production database:

| Window | Total | hermes | masfactory | manual |
|---|---|---|---|---|
| 7 days | 508 | 471 | 37 | 0 |
| 30 days | 1599 | 1336 | 256 | 7 |
| 90 days | 3238 | 2214 | 1008 | 16 |
| all time | 3238 | 2214 | 1008 | 16 |

The evaluation harness defaults to a 90-day window (`eval_app/config.py:20`). It would therefore compute all four headline metrics on 1000 of 3238 signals, discarding 69 percent of the corpus.

The truncation is not random. Because the ordering is `inserted_at DESC`, the retained slice is always the most recent, and the two systems' relative output rates differ sharply over time: hermes to masfactory is 84:16 over 30 days but 69:31 over 90 days. A metric computed on the truncated slice therefore overstates System B's share relative to a metric computed on the full window. Inter-system agreement, token efficiency per signal, and classification quality against the gold set are all affected, and the direction of the bias depends on how recently each system last ran. The last observed runs produced 116 signals for hermes and 5 for masfactory, so the skew is currently large.

**Fixed on `main` after this audit.** Both readers now request `count="exact"` and walk `.range()` windows until the collected row total reaches the server's own count, so a result that fits in one page still costs exactly one request. `id` was added as a secondary sort key, which matters because a cron tick inserts hundreds of rows sharing a near-identical `inserted_at` and ordering on that alone is not stable enough to page over. A 200000-row guard bounds the loop and logs a warning if it is ever reached.

Coverage is in `systems/api/tests/test_pagination.py` (15 tests) and `systems/evaluation/tests/test_data_access_pagination.py` (15 tests), both driving the readers against a fake client that reproduces the server cap. Verified to fail on the pre-fix code (11 failures in each file) and pass after.

Two consequences worth recording. First, `token_usage` in both modules chunked its `IN` clause at 100 run ids but left each chunk unpaged, so it had the same defect one level down; that is fixed too. Second, every metric computed before the api and evaluation code is redeployed used the truncated corpus, so any figure already carried into the thesis from a pre-fix run should be recomputed.

### 9.7 Two smaller production observations

**`public.industry_news` is stale.** It holds 120 rows spanning 2026-04-25 to 2026-06-09 and has not grown since. `reports_system.industry_news_runner` appears in no log and in no `docker ps -a` history, consistent with it having been run once by hand from the seed command at `docs/migrations.md:385` and never again. The `/quantum-news` page therefore shows nothing newer than 9 June.

**Three copies of the environment file exist, all world-readable.** `/opt/mas-deeptech-research/.env` (root, mode 644), `.env.bak` (root, mode 644, dated 2026-07-04), and `.env.save` (owned by `annageiser`, mode **664**, dated 2026-06-10). All three have distinct hashes, so `.env.bak` and `.env.save` hold older credential sets, plausibly including the superseded second OpenRouter key. All are readable by any local account. Contents were not read. The host is also at 81 percent disk (77 GB of 96 GB used), which is worth watching but not yet a problem.

### 9.8 Corrections to earlier sections of this audit

| Earlier claim | Correction |
|---|---|
| Section 6.3 and README limitation 11: neither `sync_manual_signals` nor `industry_news_runner` is scheduled | Half wrong. `sync_manual_signals` **is** scheduled nightly in the installed masfactory cron entry, which the committed sample does not contain. The claim stands for `industry_news_runner`. The underlying defect is different from what was reported: the job runs and fails, rather than never running. |
| Section 7 assumption "the dashboard is not live", and the cleanup Tier B question about whether it should be retired | The dashboard is live, has been for four weeks, and is publicly reachable without authentication. The question is no longer whether to retire it but that it is currently an unauthenticated public mirror of the dataset. |
| Section 8: production state unverifiable | Resolved throughout this section. |
| Section 8: resolved dependency versions unrecoverable | Resolved in 9.4 for the currently deployed images. Still unrecoverable for any past image. |
| Sections 9.3 and 9.6 described both defects as unfixed | Both were fixed on `main` after the audit, with regression tests verified to fail on the pre-fix code. Neither fix is deployed: the running masfactory, api and evaluation code still carries the defect until the images are rebuilt. |

## 10. Remediation record

Everything in sections 1 through 9 describes the repository and the running
system as found on 2026-08-02. This section records what was then changed, so
the audit and the tree do not drift apart. Commits are on `main`.

| Commit | Defect | Verified |
|---|---|---|
| `bb72e03` | Unranged PostgREST reads truncated silently at 1000 rows in the api and evaluation readers. The evaluation harness computed all four thesis metrics on 1000 of 3238 signals, and because the ordering was `inserted_at desc` the discarded remainder was not a random sample. | `/api/signals?limit=5000` now returns 3238 in production. 30 tests, failing 11 each on the pre-fix code. |
| `c0a4ba6` | `sync_manual_signals.py` used the pre-v0.5.0 three-column `on_conflict` key; the nightly job had failed with PostgREST 42P10 on every run since 2026-07-09. | 7 tests comparing all three writers against the constraint parsed from `schema.sql`. |
| `5344e45` | Semantic dedup searched the whole corpus, so System B's rows could suppress System A's record of the same event, contradicting the v0.5.0 per-system uniqueness key. Never actually fired (0 drops in 52 runs) but live. | `p_system` filtering confirmed against the production database. 9 tests. |
| `3025c2b` | `SKILL.md` described `dimension` as free text and two of its four worked examples used off-taxonomy labels. 88 percent of System B's July signals carried one of 214 invented labels, which also meant its headline scores were computed from `scoring.py` fallback constants rather than the signalling-theory weights. | Off-taxonomy rate on the first full 40-actor run after deploy: **0.0 percent**, down from 88.5 percent. 22 tests. |
| `17bd998` | Reports reader carried the same truncation. The web container's `HEALTHCHECK` had never passed once because Next.js standalone binds `process.env.HOSTNAME`, which Docker sets to the container id. | Container reports healthy; `localhost:3000` returns 200 from inside it. |
| `932aa63` | `package-data` globbed `persistence/*.sql`, which does not descend into `migrations/`, so neither migration shipped with the package. | Wheel installed into a clean environment carries both. |
| `f5c26f4`, `db1b209` | No gold set existed, so the precision question was unanswerable. Added a blind, system-balanced spreadsheet route over the pre-registered sampler. | 21 tests. A real 50-row sheet generated from the live corpus, balanced 25/25. |
| `56792fa` | System B lost most actors nightly to iteration-budget exhaustion (22 to 29 of 40) and discarded everything it had found. | **Not effective.** 23 of 40 after the change, inside the historical 50 to 72 percent band. The guidance is retained as correct but unproven; the defect is unresolved. |
| `71cab3a` | Four sources disagreed on System A's per-collector budget and production had adopted the lowest; `MASF_LIMIT_PRESS` and `MASF_LIMIT_PATENTS` were documented but never passed into the graph; arXiv had no retry, so a transient 429 cost an actor its whole publications channel. System A recorded zero arXiv signals in July against System B's 151. | 18 tests, failing 13 on the pre-fix code. Production `.env` moved to the documented funnel. |
| `71cab3a` | The retired Streamlit dashboard was still running on the VPS with port 8501 published and no authentication. | Container and image removed, port confirmed closed, source removed from the tree. |

Two items from section 9 remain open by decision rather than oversight, and
both are recorded in the README: System B's iteration-budget exhaustion, and
the fact that the three 2026-08-02 changes constitute a phase boundary in the
collected data.
