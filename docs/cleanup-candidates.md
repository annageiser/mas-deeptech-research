# Cleanup candidates

Unused-file analysis for commit `c0a9ea8` on branch `main`, performed 2026-08-02. Nothing in this document has been executed. No file was deleted, moved, or renamed during the audit.

## 1. Method

### 1.1 Static reachability

Reachability was computed outward from the entry points listed in [architecture-analysis.md](architecture-analysis.md) section 1.4, following actual `import`, `from`, `COPY`, `command`, and `href` edges. The import graph is in section 2 of that document.

### 1.2 Whole-tree basename sweep

Every tracked file was checked for references to both its basename and its stem across the entire tree, excluding the submodule:

```
for f in $(git ls-files | grep -v '^systems/hermes/upstream$'); do
  base=$(basename "$f"); stem="${base%.*}"
  n=$(rg -l --fixed-strings "$base" -g '!systems/hermes/upstream/**' | grep -v "^$f$" | wc -l)
  m=$(rg -l --fixed-strings "$stem" -g '!systems/hermes/upstream/**' | grep -v "^$f$" | wc -l)
  [ "$n" = "0" ] && [ "$m" = "0" ] && echo "ZERO-REF: $f"
done
```

This covers configuration files, CI definitions, Dockerfiles, templates, and string literals, because `rg` searches file contents without regard to language.

Result: 42 of 284 tracked files matched nothing anywhere. All 42 were then examined individually against the dynamic-reference mechanisms below.

### 1.3 Dynamic-reference mechanisms explicitly tested

| Mechanism | Present in this repository | Files it rescues |
|---|---|---|
| Test auto-discovery | Yes. `[tool.pytest.ini_options] testpaths = ["tests"]` in all six `pyproject.toml` files. | 8 zero-reference `test_*.py` files |
| Filesystem routing | Yes, twice. Next.js App Router loads `src/app/**/page.tsx`, `error.tsx`, `not-found.tsx`, `layout.tsx`, and `icon.png` by name. Streamlit loads `dashboard_app/pages/*.py` by directory. | 1 Next.js file, 9 Streamlit pages |
| Framework configuration by convention | Yes. `next.config.mjs` is read by name by the Next.js CLI. | 1 file |
| Plugin directories | Yes. `plugins/web/localextract` is copied at build time into the directory resolved by reimplementing `hermes_cli.plugins.get_bundled_plugins_dir` (`systems/hermes/Dockerfile:74-87`), then activated by `web.extract_backend: localextract` in `config/cli-config.yaml:149`. Neither edge is visible to static analysis. | 4 files |
| Monkeypatch at import time | Yes. `scripts/patch_web_tools_backend.py` appends a wrapper to the upstream `tools.web_tools._is_backend_available`, which hardcodes backend names. | 1 file |
| Package data globs | Yes. `[tool.setuptools.package-data]` in `systems/masfactory/pyproject.toml` includes `classification/*.yaml` and `persistence/*.sql`. Note that this glob does not match `persistence/migrations/*.sql`. | 2 files |
| Assets referenced from markup | Yes. `public/icons/quantum-favicon.png` is named in `src/app/layout.tsx:14-17`. | 1 file |
| Files consumed only by CI or packaging | Yes. `.dockerignore` files, `README.md` files required by `readme = "README.md"` in each `pyproject.toml`. | 11 files |
| Container init hooks | Yes. `seed-hermes-home.sh` is installed as `/etc/cont-init.d/03-seed-swiss-quantum` and run by s6-overlay, never called by name from another script. | 1 file |
| Dependency injection by name, service locators, reflection | Not found. No `importlib.import_module`, `getattr`-based dispatch, or entry-point registry outside the plugin case above. | none |
| Migrations auto-discovery | Not found. `schema.sql` is applied by hand in the Supabase SQL editor; no code reads either SQL file at runtime. | none |

### 1.4 Dead-code analyser

Tool: `vulture` 2.x, installed into a throwaway Python 3.11 environment.

Exact invocation:

```
vulture --min-confidence 80 systems/api/api_app systems/masfactory/masfactory_system systems/reports/reports_system systems/evaluation/eval_app systems/dashboard/dashboard_app systems/hermes/scripts systems/hermes/plugins
```

Output, in full:

```
systems/evaluation/eval_app/qda/refi_qda.py:51: unused import 'io' (90% confidence)
systems/evaluation/eval_app/qda/refi_qda.py:57: unused import 'IO' (90% confidence)
```

A second pass at `--min-confidence 60` produced 60 further hits, of which the large majority are false positives caused by patterns vulture cannot see: FastAPI route decorators (31 hits in `api_app/main.py` alone), Pydantic field validators (8 hits in `api_app/training.py`), and the upstream provider protocol that `localextract/provider.py` implements (5 hits). After checking each remaining candidate against a whole-tree search, two genuine unreferenced module-level symbols survive. They are reported in section 4 rather than section 3, because they are symbols inside otherwise-live files and are not file-removal candidates.

No dead-code analyser was run against the TypeScript tree. `ts-prune` and `knip` are not installed and installing them was out of scope for a read-only audit. TypeScript reachability was determined by reading `Nav.tsx`, the App Router directory structure, and the import graph. This is stated as a limitation, not a finding.

## 2. Classification table

Tier definitions follow the audit brief. Tier A is unreferenced with no plausible dynamic reference. Tier B is likely unused but needs a maintainer decision, with the question stated. Tier C is referenced only by documentation or by other unused files. Tier D appears unused but must be retained.

| Path | Category | Evidence of non-reference | Search commands run | Tier | Risk if removed |
|---|---|---|---|---|---|
| `systems/masfactory/masfactory_system/persistence/migrations/v0.5.0-per-system-dedup.sql` | Superseded operator artefact | Zero references tree-wide, including `docs/migrations.md`. Content is duplicated verbatim inside `schema.sql:74-113`. Not packaged: `[tool.setuptools.package-data]` includes `persistence/*.sql` only, which does not match the `migrations/` subdirectory. | `rg -n "v0.5.0-per-system-dedup"`; `rg -n "persistence/migrations\|migrations/"`; basename sweep | B | Low functionally. The migration is already applied to the live database and re-derivable from `schema.sql`. Removing it loses the standalone operator runbook, which is a records question, not a code question. **Question for the maintainer: is `persistence/migrations/` the intended home for future one-shot migrations, given that `docs/migrations.md` already serves that purpose and this file is not referenced from it?** |
| `systems/web/src/app/icon.png` | Duplicated asset | Byte-identical to `systems/web/public/icons/quantum-favicon.png`, SHA-256 `77858d58c76ddcb53621595613c8b942f5b5f925016adc0cea24d350578e1da3`. `layout.tsx:14-17` declares `icon`, `shortcut`, and `apple` all pointing at the `public/icons/` copy. | `shasum -a 256` over all tracked files, then `uniq -d`; `rg -n "icon.png\|quantum-favicon" systems/web/src systems/web/public` | B | Low, but not zero. `src/app/icon.png` is a Next.js file convention that emits its own `<link rel="icon">`. The explicit `metadata.icons` in `layout.tsx` should take precedence, but this was not verified by building and inspecting the emitted head. **Question for the maintainer: is the App Router `icon.png` convention or the explicit `metadata.icons` declaration the intended favicon source? One of the two copies is redundant.** |
| `systems/dashboard/` (entire directory, 15 files) | Superseded implementation, but **live in production** | Compose service commented out at `docker-compose.yml:270-284`. Absent from the `docker-builds` CI matrix. No Caddy route: `caddy/Caddyfile:39-45` sends the catch-all to `web-container-g:3000`. Every capability it provides is present in `systems/api` plus `systems/web`. **However**, production inspection on 2026-08-02 found `dashboard-container-d` up for four weeks as a compose orphan, with 8501 published on `0.0.0.0`, `ufw` inactive, and `curl http://187.127.87.208:8501/` returning HTTP 200 with no credentials. See [architecture-analysis.md](architecture-analysis.md) section 9.2. | `rg -n "dashboard" docker-compose.yml caddy/Caddyfile .github/workflows/ci.yml`; basename sweep over all 15 files; `docker ps`, `ss -tlnp`, `ufw status`, unauthenticated `curl` on the host | B | **The removal question is now secondary to an exposure question.** Commenting out the compose service did not stop the pre-existing container, and `restart: unless-stopped` has kept it alive across reboots. Whatever is decided about the source tree, the running container is an unauthenticated public mirror of the dataset that the rest of the site puts behind basic auth. Code-side risk of removal is unchanged and moderate: it is a green CI pytest entry (`ci.yml:44-45`), and `api_app/scoring.py:2` cites it as the origin of the vendored scoring code. **Questions for the maintainer: (a) should `dashboard-container-d` be stopped now, or moved behind Caddy? (b) independently of that, should the source tree keep the Streamlit UI as an artefact of the development history?** |
| `docs/thesis-assets/architecture_diagram.png` | Orphaned asset | Zero references tree-wide. Already staged as deleted in the working tree. | basename sweep; `rg -n "architecture_diagram"` | A | None. Nothing links it. |
| `docs/thesis-assets/render_architecture_diagram.py` | Orphaned generator | Zero references tree-wide. Not in any package, not in CI, no `__main__` consumer. Already staged as deleted in the working tree. | basename sweep; `rg -n "render_architecture_diagram"` | A | None, provided the diagram it generated is also going. If the PNG is kept, this script is what regenerates it. |
| `docs/thesis-assets/thesis_notes.md` | Orphaned document | Already staged as deleted in the working tree. The name collides with `RPT_THESIS_NOTES_PATH`, whose default is `/data/raw/thesis_notes.md`, a different path inside the bind mount. | `rg -n "thesis_notes"` | A | None. The reports container reads `/data/raw/thesis_notes.md`, not this file. Confirmed at `reports_system/config.py:21`. |
| `docs/thesis-assets/.gitkeep` | Directory placeholder | Its only purpose is to keep an otherwise-empty directory tracked. The other three files in that directory are Tier A. | `git ls-files docs/thesis-assets` | C | None. Resolve after the three Tier A files above: if they go, the directory has no reason to exist. |
| `systems/dashboard/dashboard_app/pages/1_Impact_leaderboard.py` through `9_Methodology.py` (9 files) | Convention-loaded | Zero explicit references, but Streamlit loads every file in `pages/` by directory convention. | basename sweep; `rg -n "pages/"` | D | Retain while the dashboard package is retained. They are the dashboard's actual UI. Their fate follows the Tier B decision on the package. |
| `systems/dashboard/tests/test_dashboard_skeleton.py`, `systems/evaluation/tests/test_metrics.py`, and 6 masfactory `test_*.py` files | Convention-loaded | Zero explicit references. Discovered by pytest through `testpaths = ["tests"]`. | basename sweep; `rg -n "testpaths"` in each `pyproject.toml` | D | Retain. These are 8 of the repository's passing test files. |
| `systems/web/next.config.mjs` | Convention-loaded | Zero explicit references. Read by name by the Next.js CLI. Contains the `/api/:path*` rewrite the frontend depends on. | basename sweep; `rg -n "next.config"` | D | Retain. Removing it breaks the API proxy and the standalone output mode. |
| `systems/web/src/app/not-found.tsx` | Convention-loaded | Zero explicit references. Next.js App Router 404 boundary. | basename sweep | D | Retain. |
| `docs/iterations/*.md` (18 of 33 files matched zero references) | Append-only record | Iteration records are indexed by `docs/iterations/README.md`, which links some but not all of them. Being unreferenced is their normal state. | basename sweep; `rg -n "v0.4" docs/iterations/README.md` | D | Retain. The audit brief itself weights these above general prose documentation, and they proved accurate on every spot check. They are the closest thing the repository has to an architecture decision record. |
| `docs/thesis-zotero-todo.md` | Working document | Zero references. A personal task list. | basename sweep | D | Retain. Removing another person's working notes is not a code-cleanup decision. |
| `systems/hermes/scripts/backfill_embeddings.py`, `backfill_sentiment.py` | Manual maintenance tools | Not invoked by `collect_all_actors.sh`, any crontab sample, or any Dockerfile `RUN`. Copied into the image by `COPY scripts/` (`systems/hermes/Dockerfile:113`). | `rg -n "backfill_"`; read of `collect_all_actors.sh` | D | Retain. Both have complete argparse interfaces with `--dry-run` and `--system`, and both are documented in `docs/iterations/v0.4.20-hermes-embeddings.md` and `v0.4.24-sentiment.md`. They are operator tools, not orphans. |
| `systems/reports/reports_system/industry_news_runner.py` | Manual entry point | No import from `reports_system/runner.py`. No cron sample runs it. | `rg -n "industry_news"`; read of `reports/crontab.sample` | D | Retain. It is the only writer of `public.industry_news`, which `/api/industry-news` and the `/quantum-news` page read. Removing it orphans a table and a page. The real defect is that nothing schedules it. |
| `systems/masfactory/masfactory_system/scripts/sync_manual_signals.py` | Manual entry point | Not imported anywhere. Referenced in comments at `api_app/main.py:47`, `retriever.py:187`, `schema.sql:23`, and as a command in `docs/migrations.md:712`. | `rg -n "sync_manual_signals"` | D | Retain. It is the only code path that propagates curated manual signals into `public.signals` as `system='manual'`, which `VALID_SYSTEMS` at `main.py:52` expects to exist. |
| `systems/masfactory/masfactory_system/agents/survivor.py` | Superseded node, retained by intent | Exported at `agents/__init__.py:47` and listed in `__all__`, but not among the nodes passed to `build_graph`. | `rg -n "SurvivorNode\|survivor"` | D | Retain, per the explicit statement at `graph.py:20-23` that it is kept exported for external imports while `AccumulateActor` performs the same filtering. Removing it would need that comment removed and the `__all__` entry dropped. It is 63 lines. |
| `systems/hermes/plugins/web/localextract/*` (4 files) | Dynamically loaded | Zero Python import edges from any file in this repository. | `rg -n "localextract"` across the tree | D | Retain. Loaded through the two build-time mechanisms in section 1.3. Removal silently reverts System B to snippet-only extraction, which is the exact regression the Dockerfile build assertions exist to catch. |
| `systems/hermes/scripts/seed-hermes-home.sh` | Container init hook | Called by no script. Installed as `/etc/cont-init.d/03-seed-swiss-quantum` at `systems/hermes/Dockerfile:117`. | `rg -n "seed-hermes-home\|cont-init"` | D | Retain. Without it, the upstream image's own init hook leaves a 62 KB example config whose default model is paid, which is the failure documented in `docs/iterations/v0.4.9-seed-hook-always-overwrite.md`. |
| `systems/evaluation/data/gold/labels.yaml.example` | Template | Referenced by a docstring comment at `eval_app/config.py:24`. Not read by code. | `rg -n "labels.yaml"` | D | Retain. It documents the format `EVAL_GOLD_PATH` expects; there is no other specification of that format. |
| `data/raw/.gitkeep` | Directory placeholder | The directory also holds two tracked YAML files, so the placeholder is redundant. | `git ls-files data/raw` | C | None functionally, but it is one empty file. Resolve alongside the `docs/thesis-assets/.gitkeep` decision if a placeholder cleanup is wanted at all. |
| `.mcp.json` | Editor tooling config, tracked against its own ignore rule | Matched by `.gitignore:222`. Not read by any container, script, or CI job. | `git check-ignore -v --no-index .mcp.json`; `rg -n "mcp.json"` | D | Retain the file, but the tracking status is inconsistent. See section 4. Its own comment states the repository "stays buildable and runnable without it", so it is developer convenience rather than infrastructure. |

### Summary by tier

| Tier | Count | Files |
|---|---|---|
| A | 3 | The three `docs/thesis-assets/` content files |
| B | 3 candidates covering 17 files | The standalone migration SQL, the duplicated favicon, the `systems/dashboard/` package |
| C | 2 | `docs/thesis-assets/.gitkeep`, `data/raw/.gitkeep` |
| D | 47 | Everything the basename sweep flagged that is reached by a mechanism static analysis cannot see |

## 3. Note on the Tier A files

All three Tier A files are already staged as deleted in the working tree at the time of this audit, alongside `docs/thesis-assets/.gitkeep`:

```
 D docs/thesis-assets/.gitkeep
 D docs/thesis-assets/architecture_diagram.png
 D docs/thesis-assets/render_architecture_diagram.py
 D docs/thesis-assets/thesis_notes.md
```

The audit did not create these deletions and has not committed them. The analysis above independently confirms that removing the three content files is safe, and that the `.gitkeep` becomes pointless once they go.

## 4. Additional findings

### 4.1 Duplicated files

| Files | SHA-256 | Assessment |
|---|---|---|
| `systems/web/src/app/icon.png`, `systems/web/public/icons/quantum-favicon.png` | `77858d58...` | Byte-identical, 43549 bytes each. Tier B above. |
| `systems/masfactory/masfactory_system/training_layer.py`, `systems/hermes/scripts/training_layer.py` | `8fed7f26...` | Byte-identical, 251 lines each. **Required**, not accidental: the code-sharing prohibition at `systems/hermes/Dockerfile:20-23` forbids System B importing from System A. Do not deduplicate. Consider a CI check that the two remain identical, since nothing currently detects drift. |
| `systems/dashboard/.dockerignore`, `systems/masfactory/.dockerignore`, `systems/reports/.dockerignore` | `a90e1eae...` | Three identical 6-line files. Harmless. |
| `systems/hermes/tests/__init__.py`, `systems/masfactory/masfactory_system/scripts/__init__.py`, `data/raw/.gitkeep` | `e3b0c442...` | Empty files. The two `__init__.py` files are required package markers. |

### 4.2 Superseded implementations left alongside their replacements

| Superseded | Replacement | State |
|---|---|---|
| `systems/dashboard/` (Streamlit) | `systems/api` plus `systems/web` | Compose service commented out, CI pytest entry retained, Dockerfile retained. |
| `agents/survivor.py` (`SurvivorNode`) | `AccumulateActorNode` in `agents/loop_nodes.py` | Exported, not wired. Documented as deliberate. |
| `persistence/migrations/v0.5.0-per-system-dedup.sql` | The same block inlined at `schema.sql:74-113` | Both present, neither referenced by code. |
| `signals.dimension_legacy` column and the `legacy_dimensions` mapping | `signals.dimension` on the v0.4.0 nineteen-key set | Deliberate. Preserves pre-migration reproducibility, per `schema.sql:185-193`. Not a cleanup candidate. |

### 4.3 Empty directories

None tracked. Every directory containing a tracked file contains at least one non-placeholder file, except `docs/thesis-assets/`, whose three content files are staged for deletion.

### 4.4 Committed build artefacts

None. `systems/api/build/`, `systems/api/api_app.egg-info/`, `systems/web/.next/`, `systems/web/node_modules/`, all `__pycache__/` directories, all `.pytest_cache/` directories, and eleven `.DS_Store` files exist on disk and are all correctly excluded by `.gitignore`. Verified with `git status --porcelain --ignored`.

### 4.5 Committed secrets and credential files

None found. The scan in [architecture-analysis.md](architecture-analysis.md) section 1.5 returned nothing. Three placeholder values are committed and are documented as deploy-time substitutions:

| Placeholder | Location | Substitution documented at |
|---|---|---|
| `PLACEHOLDER_HASH_REPLACE_BEFORE_DEPLOY` bcrypt string | `caddy/Caddyfile:32` | `caddy/Caddyfile:33-36` |
| `ultrasecretkey` | `searxng/settings.yml:24` | `searxng/settings.yml:9-11` and `.env.example` |
| Empty values throughout | `.env.example` | The file is a template by design |

The risk is not that a secret is committed but that a deploy which skips the substitution ships the placeholder. Nothing in the repository enforces the substitution, and nothing detects it after the fact.

### 4.6 Stale lockfiles

`systems/web/package-lock.json` is current: all nine direct dependencies resolve to exactly their `package.json` pins, and `npm ci` in CI would fail if the two disagreed.

No Python lockfile exists at all, in any of the six packages. This is a more serious reproducibility gap than a stale lockfile would be, because there is nothing to be stale. See [architecture-analysis.md](architecture-analysis.md) section 1.2.

### 4.7 Unreferenced symbols inside live files

These are not file-removal candidates. Each was confirmed by whole-tree search after appearing in the vulture pass.

| Symbol | Location | Evidence |
|---|---|---|
| `collect_industry_news_unattributed` | `systems/masfactory/masfactory_system/collection/rss.py:187` | Its docstring says it is "Used by a separate cron job that populates public.industry_news". That job is `reports_system/industry_news_runner.py`, which deliberately does not import masfactory and re-implements the logic instead. So the intended caller exists but cannot call it. `rg -n "collect_industry_news_unattributed"` matches only the definition and a cross-reference comment at `rss.py:138`. |
| `build_fallback_model` | `systems/masfactory/masfactory_system/model.py:230` | `runner.py` calls `build_main_model` only; the failover model is constructed inside the failover wrapper. `rg -n "build_fallback_model"` matches only the definition. |
| `io` and `IO` imports | `systems/evaluation/eval_app/qda/refi_qda.py:51,57` | The only two findings vulture reported at 80 percent confidence. |

### 4.8 Configuration keys read by nothing

Seven keys are documented in `.env.example` but read by no source file in this repository, and none is forwarded by `docker-compose.yml`:

`HRM_LIMIT_ACTORS` (line 131), `HRM_MAX_ITERATIONS` (132), `HRM_SEMANTIC_DEDUP` (150), `HRM_SEMANTIC_DEDUP_THRESHOLD` (151), `HRM_SEMANTIC_DEDUP_DAYS` (152), `GEMINI_API_KEY` (190), `TELEGRAM_BOT_TOKEN` (192).

Additionally, `TAVILY_API_KEY` is declared twice, at `.env.example:94` and `.env.example:191`. When the file is sourced, the second occurrence wins silently.

The five `HRM_*` keys matter beyond tidiness: `docs/architecture.md:242` describes System B semantic dedup as an available capability gated on `HRM_SEMANTIC_DEDUP`. No such gate exists in `persist_signals.py`, which reads only `HRM_EMBEDDINGS` and `HRM_SENTIMENT`. The documented capability is not implemented on the System B side.

### 4.9 Tracked against an ignore rule

`.mcp.json` is matched by `.gitignore:222` and is tracked. Either the ignore rule or the tracking is wrong. The file's own comment block states the repository stays buildable and runnable without it, which argues for untracking; the fact that it is a project-shared editor configuration argues for removing the ignore rule. This is a maintainer decision, not a defect the audit can resolve.

## 5. Removal script

The block below covers Tier A only. It is commented out.

```bash
# WARNING
# ------------------------------------------------------------------
# REVIEW EVERY LINE BEFORE EXECUTING. This script has not been run.
# It removes only the three Tier A files: content assets under
# docs/thesis-assets/ that no file in the repository references.
#
# These three paths are ALREADY staged as deletions in the working
# tree at the time of this audit. If that staging is committed, these
# commands become no-ops and can be skipped entirely. Check first:
#
#     git status --porcelain docs/thesis-assets
#
# The fourth file in that directory, docs/thesis-assets/.gitkeep, is
# Tier C: remove it only after deciding that the directory itself is
# going, and be aware that removing the last tracked file in a
# directory removes the directory from git's view.
#
# Nothing in Tier B is included here. Those three candidates each
# carry an open question for the maintainer; see section 2.
# ------------------------------------------------------------------

# git rm docs/thesis-assets/architecture_diagram.png
# git rm docs/thesis-assets/render_architecture_diagram.py
# git rm docs/thesis-assets/thesis_notes.md

# Tier C, only if the directory is being retired along with the three
# files above:
# git rm docs/thesis-assets/.gitkeep

# After any of the above, verify nothing broke:
# rg -n "thesis-assets|architecture_diagram|render_architecture_diagram"
# (expect: only matches inside docs/architecture-analysis.md and
#  docs/cleanup-candidates.md, which are this audit's own output)
```

## 6. What this analysis could not determine

- **TypeScript reachability was established by reading, not by tooling.** No `ts-prune` or `knip` run backs the conclusion that all 27 `.tsx` files and all 5 `.ts` files are reachable. Installing a TypeScript dead-code analyser and running it would resolve this.
- **Whether the Next.js `icon.png` convention or the explicit `metadata.icons` declaration wins at runtime.** Determining this requires building the frontend and inspecting the emitted document head. The audit did not build the image.
- **Whether any of the 33 iteration documents describe work that was later reverted.** Each was spot-checked for accuracy against current code where it made a structural claim, but no systematic reversal check was performed across all of them.
- **Whether `systems/dashboard` is still used by anyone.** The repository shows it is not routed and not built. Whether someone reaches it by SSH tunnel on the production host, as `docs/dns-and-dashboard.md` once instructed, is not observable from here.

## 7. Production cross-check

The classifications above were re-checked against the running system on 2026-08-02 by read-only SSH inspection. Full results are in [architecture-analysis.md](architecture-analysis.md) section 9. Two entries in this document changed as a result.

| Entry | Repository-only conclusion | After production inspection |
|---|---|---|
| `systems/dashboard/` | Superseded and dormant | Superseded in the compose file but running and publicly exposed. Row above revised. |
| `sync_manual_signals.py` (Tier D, retain) | Retain; unscheduled | Retain, and it **is** scheduled, through a chained step in the installed masfactory cron entry that the committed sample omits. It has failed on every run since 2026-07-09 with PostgREST error 42P10 because its `on_conflict` key was not updated for v0.5.0. Retention is now clearly correct, and the file needs a one-line fix rather than a scheduling decision. |
| `industry_news_runner.py` (Tier D, retain) | Retain; unscheduled | Confirmed. Never run since a one-off manual seeding; `public.industry_news` holds 120 rows spanning 2026-04-25 to 2026-06-09 and has not grown. |
| `persistence/migrations/v0.5.0-per-system-dedup.sql` (Tier B) | Duplicated by `schema.sql`, safe to consider for removal | Unchanged as a file-removal question, but the migration's operator note at line 8 names only two of the three `on_conflict` call sites that needed updating, which is the direct cause of the failure above. The file has documentary value as the record of that omission. Recommend retaining until the third call site is fixed. |
| Everything else | unchanged | No other classification changed. |

No Tier A classification changed. The removal script in section 5 remains valid and remains unexecuted.

## 8. Disposition

Acted on 2026-08-02, after the audit.

| Candidate | Tier | Outcome |
|---|---|---|
| `systems/dashboard/` (20 files) | B | **Removed** (`71cab3a`). The maintainer confirmed it is no longer needed. The Tier B question turned out to be secondary: the package was dormant in the repository but the container was live on the VPS with port 8501 published and no authentication. Container and image removed from the host, port confirmed closed, package and its CI matrix entry removed, two provenance comments in `api_app` reworded so they do not dangle. Source remains in git history. |
| `docs/thesis-assets/` content files | A | Committed as deleted, as staged. |
| `persistence/migrations/*.sql` not packaged | B | **Resolved the other way** (`932aa63`). Rather than removing the standalone migration, the `package-data` glob was widened so both migrations ship with the package. CI had already tripped over the gap. |
| `systems/web/src/app/icon.png` duplicate | B | Left in place. Untested which of the two favicon declarations Next.js honours, and a deadline week is the wrong time to find out. |
| Everything at Tier C and D | C, D | Unchanged, as classified. |
