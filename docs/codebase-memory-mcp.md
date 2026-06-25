# codebase-memory-mcp — code-intelligence MCP for the dev workflow

**Upstream:** <https://github.com/DeusData/codebase-memory-mcp>
**License:** MIT
**Role in this project:** local code-intelligence tool used by AI editor
clients (Claude Code, Cursor, Continue) — **not a production runtime
dependency**.

## What it gives you

A persistent knowledge graph of the repo's *source code* (functions,
classes, files, modules, calls, imports), indexed by a single static C
binary into `~/.cache/codebase-memory-mcp/`. Queries are sub-millisecond
over a Cypher-subset; 158 languages supported via vendored tree-sitter.

When you open this repo in Claude Code (or any MCP-aware editor with
`.mcp.json` support), the editor's MCP client auto-launches the server
and exposes 14 tools to the LLM:

```
index_repository    search_graph         trace_path
query_graph         detect_changes       get_architecture
manage_adr          (+ 7 more)
```

The LLM can answer questions like *"what calls `_strip_reasoning_artefacts`?"*
or *"which routes use the supabase service-role key?"* without reading
every file end-to-end. Token cost on AI sessions drops sharply.

## What it does NOT do here

- **No runtime in Docker.** `masfactory`, `hermes`, `reports`, `api`,
  `web`, `caddy`, `dashboard`, `phoenix` — none of the seven compose
  services depends on it.
- **No CI dependency.** `.github/workflows/ci.yml` does not invoke it.
- **No data ingestion of research entities.** The MCP indexes *source
  code only*. Actors, signals, signal_types, dimensions live in
  Supabase and are visualised by the web knowledge-graph (`/graph`
  page → `systems/api/api_app/knowledge_graph.py`). The two graphs
  have separate domains, separate storage, separate query paths.
  See [v0.4.40 iteration doc](iterations/v0.4.40-codebase-memory-and-knowledge-graph.md)
  for the rationale.
- **Not on the thesis-submission critical path.** The repo builds,
  runs, deploys, and the eval harness produces correct results
  whether or not the binary is installed. If you skip the install,
  the editor's MCP client emits one "tool unavailable" warning and
  carries on.

## Install (one-time, per dev machine)

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh \
  | bash
```

The script downloads the latest signed release from the GitHub
Releases page (SLSA Level 3, VirusTotal-scanned) and drops the binary
into `$HOME/.local/bin/codebase-memory-mcp` — make sure that's on
`$PATH`.

Verify:

```bash
codebase-memory-mcp --version
# expected: v0.8.1 or later
```

### Alternatives

- Homebrew (macOS): `brew install codebase-memory-mcp` (when the tap
  is published — check upstream)
- npm: `npm install -g codebase-memory-mcp`
- PyPI: `pip install codebase-memory-mcp`
- Build from source: C compiler + zlib (~30 seconds on a modern laptop)

## First-time index

From the repo root:

```bash
codebase-memory-mcp index . --cache-dir .codebase-memory
```

Takes seconds on this repo (~7 MB of source under `systems/`). The
`.codebase-memory/` folder is git-ignored except for `graph.db.zst`
(see below).

## Editor integration

`.mcp.json` at the repo root configures every MCP-aware client. Claude
Code, Cursor, Windsurf, Continue, and Aider all pick this up
automatically. No per-editor config needed.

To verify in Claude Code: `/mcp` from any session lists active servers
— `codebase-memory` should appear with 14 tools available.

## Updates

```bash
codebase-memory-mcp update
```

Or re-run the install script — it idempotently bumps to the latest.

### Pinning to a known-good version

For reproducibility (e.g. for thesis defence), pin a specific release
via the install URL:

```bash
curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/v0.8.1/install.sh \
  | CBM_VERSION=v0.8.1 bash
```

The version string `v0.8.1` is the release this iteration was tested
against — captured here, in [v0.4.40](iterations/v0.4.40-codebase-memory-and-knowledge-graph.md),
and in the optional `.codebase-memory/.tested-with` file (created on
first index).

## Team-shared baseline (optional)

If multiple people work on the repo and you want a consistent baseline
index, export a compressed snapshot:

```bash
codebase-memory-mcp export .codebase-memory/graph.db.zst
git add .codebase-memory/graph.db.zst
git commit -m "chore: refresh codebase-memory baseline"
```

`.gitignore` already allows this single file through the
`.codebase-memory/` exclusion. Co-workers do `codebase-memory-mcp
import .codebase-memory/graph.db.zst` to seed their local index.

For a solo thesis we recommend NOT committing the baseline — it stales
quickly with the v0.4.x iteration cadence and the index re-builds in
seconds anyway.

## Pruning

```bash
codebase-memory-mcp clean --older-than 30d
```

Or just `rm -rf .codebase-memory/` and re-index. The binary stores
nothing outside this directory.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Editor says "tool unavailable" | binary not on `$PATH` | re-run install script, restart editor |
| `index_repository` is slow | repository is huge or under WSL bind mount | run from a native filesystem; increase `CBM_WORKERS` |
| Stale results after refactor | incremental index missed a commit | `codebase-memory-mcp index . --force` |
| Conflicting MCP names | another server also named `codebase-memory` | rename one entry in `.mcp.json` |

## Why this is kept separate from the production stack

The architectural separation is deliberate:

1. The MCP server's data model is **source-code-centric**: nodes
   (Project, Package, File, Class, Function, Method, Interface, Route)
   and edges (CONTAINS_FILE, CALLS, IMPORTS, IMPLEMENTS, TESTS) only
   make sense for code artefacts. Forcing research entities (actors,
   signals) into Class / Method slots would be semantic misuse.
2. The research knowledge graph (web `/graph` page) is **research-data-centric**:
   actors, signal types, dimensions, semantic similarity between
   actors. Its storage is Supabase + pgvector, its access path is the
   FastAPI `/api/knowledge-graph` route, its lifecycle is tied to
   the daily cron output.
3. Mixing the two would require new schema, new ETL, new failure
   modes — for zero net analytical gain on either side.

We **do** reuse the conceptual pattern across both layers (typed
entities, typed relationships, semantic links between similar
entities) — that part lives in
[systems/api/api_app/kg_model.py](../systems/api/api_app/kg_model.py)
and is the same shape both the MCP and the web graph use, just over
different data domains.

See [v0.4.40 iteration doc](iterations/v0.4.40-codebase-memory-and-knowledge-graph.md)
for the full architecture analysis.
