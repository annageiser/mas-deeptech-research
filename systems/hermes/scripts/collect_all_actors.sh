#!/usr/bin/env bash
# Loop over every actor in /data/raw/actors.yaml and invoke the real
# Hermes CLI with our Swiss-quantum skill. Output is parsed JSON-by-JSON
# and upserted into Supabase as system='hermes', tied to a single
# public.runs row that's created at start + closed at end.
#
# v0.4.18: bash (not sh) because dash's `read` with non-whitespace IFS
# collapses consecutive empty TSV fields. Actor metadata was landing in
# the wrong prompt slots (Aliases got Category's value, etc.).
#
# Bind-mount contract (from docker-compose.yml):
#   /data/raw/actors.yaml   — read-only host actors file
#   /opt/data/state/        — agent memory + per-actor trajectory logs
#
# Environment:
#   HERMES_LIMIT_ACTORS     — int, cap for smoke tests (default: unset = all)
#   HERMES_LOOKBACK_DAYS    — int, lookback window (default: 180)
#   SUPABASE_URL            — required
#   SUPABASE_SERVICE_KEY    — required
#   OPENROUTER_API_KEY      — required (read by the agent's OpenRouter provider)
#   TAVILY_API_KEY (or one of EXA / BRAVE_SEARCH / FIRECRAWL / PARALLEL)
#                           — required for the agent's web_search + web_extract
#
# Exit codes:
#   0  — completed without fatal errors (per-actor failures logged, not raised)
#   2  — missing required env var
#   3  — actors.yaml not found

set -eu

ACTORS_FILE="${ACTORS_FILE:-/data/raw/actors.yaml}"
LIMIT="${HERMES_LIMIT_ACTORS:-0}"
LOOKBACK="${HERMES_LOOKBACK_DAYS:-180}"
LOGDIR="${HERMES_HOME:-/opt/data}/state/runs/$(date -u +%Y%m%dT%H%M%SZ)"
PERSIST=/opt/swiss-quantum/scripts/persist_signals.py

# v0.4.13: Hermes uses Rich for output formatting. Rich auto-wraps text
# to terminal width (default 80 cols when stdout is not a TTY), which
# breaks the agent's JSON string values across multiple lines —
# json.loads() then rejects them. Tell Rich to use a very wide
# "terminal" so it doesn't wrap inside the JSON values.
export COLUMNS=10000

# ── preflight ────────────────────────────────────────────────────────────
for var in SUPABASE_URL SUPABASE_SERVICE_KEY OPENROUTER_API_KEY; do
    eval "v=\${${var}:-}"
    if [ -z "${v}" ]; then
        echo "FATAL: ${var} is not set" >&2
        exit 2
    fi
done

# v0.4.14: ddgs (DuckDuckGo) is installed in the image as the free
# unlimited web_search backend — no API key needed. Search-provider
# keys (TAVILY_API_KEY / FIRECRAWL_API_KEY / etc) are still honored if
# set: upstream tries firecrawl/parallel/tavily/exa/brave/ddgs in
# priority order. Without any paid key, ddgs serves web_search and
# web_extract is unavailable; the agent falls back to using search
# snippets as evidence (see the skill).
if [ -n "${TAVILY_API_KEY:-}${EXA_API_KEY:-}${BRAVE_SEARCH_API_KEY:-}${FIRECRAWL_API_KEY:-}${PARALLEL_API_KEY:-}${FIRECRAWL_API_URL:-}" ]; then
    echo "[collect_all_actors] paid search backend detected (web_extract enabled)"
else
    echo "[collect_all_actors] using ddgs (DuckDuckGo, free unlimited); web_extract unavailable, agent uses snippets"
fi

if [ ! -f "${ACTORS_FILE}" ]; then
    echo "FATAL: actors file not found at ${ACTORS_FILE}" >&2
    exit 3
fi

mkdir -p "${LOGDIR}"
echo "[collect_all_actors] log dir: ${LOGDIR}"
echo "[collect_all_actors] lookback: ${LOOKBACK}d  limit: ${LIMIT:-all}"

# v0.4.18: prune per-run audit folders older than 30 days. Each run writes
# ~80 files (40 actors × stdout+stderr); after 30 days that's ~2400 files
# in the hermes_state volume. Cheap to delete here at run start.
PRUNE_BASE="${HERMES_HOME:-/opt/data}/state/runs"
if [ -d "${PRUNE_BASE}" ]; then
    PRUNED=$(find "${PRUNE_BASE}" -mindepth 1 -maxdepth 1 -type d -mtime +30 \
               -print -exec rm -rf {} \; 2>/dev/null | wc -l | tr -d ' ')
    [ "${PRUNED:-0}" -gt 0 ] && echo "[collect_all_actors] pruned ${PRUNED} run dirs older than 30d"
fi

# ── extract actors via python (yaml parsing in shell is masochism) ──────
ACTOR_LIST="${LOGDIR}/actors.tsv"
python3 - <<PY > "${ACTOR_LIST}"
import sys, yaml
with open("${ACTORS_FILE}", "r", encoding="utf-8") as f:
    data = yaml.safe_load(f) or {}
actors = data.get("actors", [])
limit = int("${LIMIT}" or 0)
if limit > 0:
    actors = actors[:limit]
for a in actors:
    slug = a.get("slug", "")
    name = a.get("name", "")
    aliases = ",".join(a.get("aliases", []) or [])
    # actors.yaml uses 'homepage', NOT 'website' (v0.4.18 fix).
    website = a.get("homepage", "") or a.get("website", "")
    cat = a.get("category", "")
    if not slug or not name:
        continue
    # TSV: slug<TAB>name<TAB>aliases<TAB>website<TAB>category
    print(f"{slug}\t{name}\t{aliases}\t{website}\t{cat}")
PY

N=$(wc -l < "${ACTOR_LIST}" | tr -d ' ')
echo "[collect_all_actors] ${N} actors to process"

# ── create the runs row (must exist before any signals are inserted) ────
RUN_ID=$(python3 "${PERSIST}" --create-run)
if [ -z "${RUN_ID}" ]; then
    echo "FATAL: failed to create runs row" >&2
    exit 1
fi
echo "[collect_all_actors] run_id: ${RUN_ID}"

# Trap: ensure we close the run row even if we exit unexpectedly.
# The trap stays "running" → "error" until the explicit close at the end.
RUN_CLOSED=0
close_run() {
    if [ "${RUN_CLOSED}" = "0" ]; then
        python3 "${PERSIST}" --close-run --run-id "${RUN_ID}" \
            --status error --error-message "shell interrupted before normal close" \
            >/dev/null 2>&1 || true
    fi
}
trap close_run EXIT INT TERM

# ── per-actor loop ───────────────────────────────────────────────────────
OK=0
FAIL=0
SIGNALS=0
while IFS="$(printf '\t')" read -r slug name aliases website category; do
    [ -z "${slug}" ] && continue

    PROMPT=$(cat <<EOF
Use the collect-swiss-quantum-signals skill to find signals for this actor.

Actor: ${slug}
Name: ${name}
Aliases: ${aliases}
Website: ${website}
Category: ${category}

Lookback: ${LOOKBACK} days.

Output the JSON block as specified by the skill. Nothing else.
EOF
)

    AGENT_OUT="${LOGDIR}/${slug}.stdout.txt"
    AGENT_ERR="${LOGDIR}/${slug}.stderr.txt"

    echo "[collect_all_actors] ▶ ${slug}"

    # v0.4.12: dropped `--quiet`. Interactive testing showed `hermes chat`
    # works perfectly without --quiet (exits 0, returns real JSON) but
    # silently exits non-zero under --quiet + redirected stdout. Root
    # cause unclear (upstream bug, maybe interactive-only auth path); the
    # output we lose to --quiet is just the banner + tool-progress
    # decorations, which the parser ignores anyway.
    #
    # </dev/null closes stdin so any upstream interactive prompt (if it
    # ever appears) fails fast instead of blocking forever.
    #
    # --model + --provider take precedence over config.yaml as
    # belt-and-braces against config drift (see v0.4.9 trail).
    # FREE-ONLY POLICY (v0.4.8): every model slug in this codebase ends
    # in `:free`. If you need a different model, override via $HERMES_MODEL.
    MODEL="${HERMES_MODEL:-nvidia/nemotron-3-super-120b-a12b:free}"
    # v0.4.19: skill set widened. Beyond our methodology skill + arxiv,
    # we also load `blogwatcher` (RSS monitoring), `company-research`
    # (structured per-company dossier), and `scrapling` (page extraction
    # fallback when ddgs snippets aren't enough). All are bundled in the
    # upstream image (75 skills total — see Hermes Doctor at first boot).
    #
    # `research-paper-writing` and `searxng-search` are documented in
    # the backlog but not loaded here — research-paper-writing fits the
    # thesis-writing workflow more than per-actor cron; searxng-search
    # needs a self-hosted SearXNG instance we don't run.
    if timeout 600 hermes chat \
            --skills collect-swiss-quantum-signals,arxiv,blogwatcher,company-research,scrapling \
            --toolsets web,skills \
            --model "${MODEL}" \
            --provider openrouter \
            -q "${PROMPT}" \
            < /dev/null \
            > "${AGENT_OUT}" 2> "${AGENT_ERR}"; then
        # Parse + persist; the persister returns the number of NEW signals inserted.
        if NEW=$(python3 "${PERSIST}" \
                    --actor-slug "${slug}" \
                    --stdin-file "${AGENT_OUT}" \
                    --run-id "${RUN_ID}" \
                    --run-log "${LOGDIR}/persist.log"); then
            SIGNALS=$((SIGNALS + NEW))
            OK=$((OK + 1))
            echo "[collect_all_actors] ✓ ${slug} — ${NEW} new signals"
        else
            FAIL=$((FAIL + 1))
            echo "[collect_all_actors] ✗ ${slug} — persist failed (see ${LOGDIR}/persist.log)"
        fi
    else
        FAIL=$((FAIL + 1))
        echo "[collect_all_actors] ✗ ${slug} — agent timed out or errored"
    fi
done < "${ACTOR_LIST}"

# ── close the run row ────────────────────────────────────────────────────
if [ "${FAIL}" -eq 0 ]; then
    STATUS=ok
    ERR_MSG=""
else
    STATUS=error
    ERR_MSG="${FAIL} of ${N} actors failed (see ${LOGDIR}/persist.log)"
fi
python3 "${PERSIST}" --close-run --run-id "${RUN_ID}" --status "${STATUS}" \
    ${ERR_MSG:+--error-message "${ERR_MSG}"} >/dev/null
RUN_CLOSED=1
trap - EXIT INT TERM

echo ""
echo "[collect_all_actors] DONE  run=${RUN_ID}  actors=${N}  ok=${OK}  fail=${FAIL}  signals=${SIGNALS}"
echo "[collect_all_actors] full logs: ${LOGDIR}"

exit 0
