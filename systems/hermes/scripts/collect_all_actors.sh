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

# v0.5.0 Stage 2 / v0.5.1 Stage 2b: the default free substrate is now
# SearXNG for web_search (self-hosted, no key) + our local full-text
# provider for web_extract (plugins/web/localextract; httpx + selectolax,
# no key), pinned explicitly in cli-config.yaml (web.search_backend=searxng,
# web.extract_backend=localextract). So in the default config the agent has
# BOTH search AND full-text extraction for free — web_extract is no longer
# gated on a paid key. Paid keys, if set, still take auto-detect precedence
# for anything not explicitly pinned; we record that for the audit trail.
#
# v0.4.36: HERMES_TOOL_STATUS lets the eval harness distinguish "agent ran
# with full tools and found nothing" (substantive zero) from "agent had no
# extraction tools available — signals: [] is mechanical not substantive"
# (§3.5, Phase 4 finding G-15). With Stage 2b, the free path is no longer a
# mechanical-zero risk; the status now records the actual substrate.
if [ -n "${TAVILY_API_KEY:-}${EXA_API_KEY:-}${BRAVE_SEARCH_API_KEY:-}${FIRECRAWL_API_KEY:-}${PARALLEL_API_KEY:-}${FIRECRAWL_API_URL:-}" ]; then
    echo "[collect_all_actors] paid search backend detected; extract pinned to localextract (full-text enabled)"
    export HERMES_TOOL_STATUS="paid+localextract"
else
    echo "[collect_all_actors] free substrate: SearXNG search + localextract full-text (web_extract enabled, no key)"
    export HERMES_TOOL_STATUS="searxng+localextract"
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

# v0.4.37 — editorial training-layer preflight. Materialises per-actor
# context blocks (manual signals + due RSS sources) into ${LOGDIR}/training/
# so each per-actor prompt can splice them in. Best-effort: failures
# leave empty files behind and the prompts proceed without the block.
python3 /opt/swiss-quantum/scripts/training_context_preflight.py \
    --log-dir "${LOGDIR}" \
    --actors-tsv "${ACTOR_LIST}" \
    >> "${LOGDIR}/training_preflight.log" 2>&1 || true

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
# v0.4.28: switched from `IFS=TAB read -r slug name aliases website category`
# to per-field `cut -f` extraction. The IFS-read approach collapses empty
# middle fields under dash/sh and (on at least the production Hermes
# container) under bash too — causing aliases/website/category to shift
# left when an actor has no aliases. Symptom: the prompt named the
# category as the "Website" field, the agent searched for
# "national_initiative quantum 2026", got nothing, and returned
# signals: [] every day. cut -f handles empty fields correctly under
# every POSIX shell.

OK=0
FAIL=0
SIGNALS=0
while IFS= read -r line; do
    [ -z "${line}" ] && continue
    slug=$(printf '%s' "${line}"     | cut -f1)
    name=$(printf '%s' "${line}"     | cut -f2)
    aliases=$(printf '%s' "${line}"  | cut -f3)
    website=$(printf '%s' "${line}"  | cut -f4)
    category=$(printf '%s' "${line}" | cut -f5)
    [ -z "${slug}" ] && continue

    # v0.4.37 — splice the editorial training-layer block if the preflight
    # produced one for this actor.
    TRAINING_BLOCK_FILE="${LOGDIR}/training/${slug}.txt"
    TRAINING_BLOCK=""
    if [ -s "${TRAINING_BLOCK_FILE}" ]; then
        TRAINING_BLOCK="$(cat "${TRAINING_BLOCK_FILE}")"
    fi

    PROMPT=$(cat <<EOF
Use the collect-swiss-quantum-signals skill to find signals for this actor.

Actor: ${slug}
Name: ${name}
Aliases: ${aliases}
Website: ${website}
Category: ${category}

Lookback: ${LOOKBACK} days.
${TRAINING_BLOCK}
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
    #
    # v0.4.30: default changed from nvidia/nemotron-3-super-120b-a12b:free
    # to a plain instruct model. Nemotron Super 120B is a REASONING model
    # that emits everything inside <think> tokens; Hermes's response
    # parser can't unwrap it, so the visible output is always empty and
    # the persister sees signals:[] regardless of how many real search
    # hits the tool calls returned. Interactive `hermes chat` confirmed
    # this with the diagnostic chain "Thinking-only response — prefilling
    # to continue → Empty response from model → Returning empty" for every
    # actor for weeks.
    #
    # v0.4.31: default changed from meta-llama/llama-3.3-70b-instruct:free
    # to qwen/qwen-2.5-72b-instruct:free. Llama-3.3-70B is the most-
    # popular free model on OpenRouter and gets rate-limited at the
    # upstream provider (Venice) within seconds.
    #
    # v0.4.32: Qwen 2.5 72B was moved from free to paid by OpenRouter.
    # Symptom: HTTP 404 "This model is unavailable for free."
    # Switched to mistralai/mistral-nemo:free. Then mistral-nemo was
    # ALSO moved to paid the same day. OpenRouter's free tier shifts
    # under us constantly.
    #
    # v0.4.33: switched to nousresearch/hermes-3-llama-3.1-405b:free.
    # Failed in production with HTTP 404 "No endpoints found that
    # support tool use" — the model itself supports tools, but the
    # FREE-TIER providers serving it don't expose tool-calling.
    #
    # v0.4.34: switched to openai/gpt-oss-120b:free. ALSO turned out
    # to be a reasoning model — same "Thinking-only response —
    # prefilling to continue → Empty response from model → Returning
    # empty" symptom as Nemotron. gpt-oss is OpenAI's open-source
    # release of a reasoning architecture; the slug doesn't contain
    # the usual "thinking"/"r1" markers but the behaviour is the
    # same.
    #
    # v0.4.35: switched to meta-llama/llama-3.2-3b-instruct:free.
    # The free-tier model selection has FOUR constraints now:
    #   1. Free (price=0)
    #   2. Not a reasoning model — slug-name detection is unreliable
    #      (gpt-oss-120b looked plain but wraps everything in <think>)
    #   3. Tool-calling supported on at least one free provider
    #   4. Not rate-limited into oblivion (Llama-3.3-70B :free is)
    # Llama 3.2 3B is the smallest reliable Llama. Small enough to
    # avoid the rate-limit pressure of the popular models, well-
    # known to support tool calling, plain instruct (no thinking
    # wrapper). Capability trade-off: classification quality is
    # weaker than a 70B+ model would produce, but the alternative
    # is signals: [] every run.
    #
    # v0.4.38: both systems migrated to nvidia/nemotron-3-ultra-550b-a55b:free
    # (frontier-class reasoning model, PAID). The historical "Hermes
    # parser cannot unwrap <think>" issue is handled by a three-layer
    # defence — see docs/iterations/v0.4.38-nemotron-3-ultra-migration.md.
    # L1 server-side reasoning-exclude in cli-config.yaml; L2 client-side
    # <think>-strip in persist_signals.py; L3 fallback retry below.
    #
    # If the primary errors or returns signals: [] for a single actor,
    # we retry that actor once with $HERMES_MODEL_FALLBACK (default
    # qwen/qwen3-next-80b-a3b-instruct:free — a free plain-instruct
    # model so a paid-credit outage cannot blank an entire run).
    #
    # Live diagnostic — list currently-available models on OpenRouter:
    #   curl -s https://openrouter.ai/api/v1/models | python3 -c \
    #     "import json,sys; d=json.load(sys.stdin); \
    #      [print(m['id']) for m in d['data']]"
    MODEL="${HERMES_MODEL:-nvidia/nemotron-3-ultra-550b-a55b:free}"
    MODEL_FALLBACK="${HERMES_MODEL_FALLBACK:-qwen/qwen3-next-80b-a3b-instruct:free}"
    # v0.4.26b: skill list pared back to those bundled in
    # nousresearch/hermes-agent:v2026.6.5 (the official image v0.4.20
    # switched to). `company-research` and `scrapling` were listed in
    # the v0.4.19 widening (task #122) but the official image rejects
    # them with `Error: Unknown skill(s): company-research, scrapling`,
    # which 100%-failed every cron tick starting 2026-06-12. The
    # currently-known-good set:
    #   - collect-swiss-quantum-signals: our methodology skill
    #   - arxiv: bundled, paper search
    #   - blogwatcher: bundled, RSS monitoring
    # To re-add scrapling-style page extraction or per-company dossier
    # building, first run `docker compose run --rm hermes hermes doctor`
    # against this image to enumerate available skills, then update this
    # list with the verified names.
    # v0.4.38 — L3 fallback. Try primary first; if it errors OR returns
    # zero signals (a strong indicator the agent's parser dropped the
    # answer because the model emitted reasoning-only content the
    # persister's L2 strip could not recover), retry the actor once
    # with $HERMES_MODEL_FALLBACK. Records which model produced the
    # accepted signals into the per-actor stderr for audit.
    _run_agent_for_actor() {
        local model_id="${1}"
        local out_file="${2}"
        local err_file="${3}"
        timeout 600 hermes chat \
            --skills collect-swiss-quantum-signals,arxiv,blogwatcher \
            --toolsets web,skills \
            --model "${model_id}" \
            --provider openrouter \
            -q "${PROMPT}" \
            < /dev/null \
            > "${out_file}" 2> "${err_file}"
    }

    USED_MODEL="${MODEL}"
    NEW=0
    AGENT_OK=0
    if _run_agent_for_actor "${MODEL}" "${AGENT_OUT}" "${AGENT_ERR}"; then
        AGENT_OK=1
    fi

    if [ "${AGENT_OK}" = "1" ]; then
        if NEW=$(python3 "${PERSIST}" \
                    --actor-slug "${slug}" \
                    --stdin-file "${AGENT_OUT}" \
                    --run-id "${RUN_ID}" \
                    --run-log "${LOGDIR}/persist.log"); then
            : # persisted fine
        else
            NEW=""
        fi
    fi

    # Retry path: primary errored OR returned zero parseable signals.
    if [ "${AGENT_OK}" = "0" ] || [ -z "${NEW}" ] || [ "${NEW}" = "0" ]; then
        if [ -n "${MODEL_FALLBACK}" ] && [ "${MODEL_FALLBACK}" != "${MODEL}" ]; then
            echo "[collect_all_actors] ↻ ${slug} — retry with fallback (${MODEL_FALLBACK})"
            FALLBACK_OUT="${LOGDIR}/${slug}.fallback.stdout.txt"
            FALLBACK_ERR="${LOGDIR}/${slug}.fallback.stderr.txt"
            if _run_agent_for_actor "${MODEL_FALLBACK}" "${FALLBACK_OUT}" "${FALLBACK_ERR}"; then
                if FB_NEW=$(python3 "${PERSIST}" \
                            --actor-slug "${slug}" \
                            --stdin-file "${FALLBACK_OUT}" \
                            --run-id "${RUN_ID}" \
                            --run-log "${LOGDIR}/persist.log"); then
                    if [ -n "${FB_NEW}" ] && [ "${FB_NEW}" != "0" ]; then
                        NEW="${FB_NEW}"
                        AGENT_OK=1
                        USED_MODEL="${MODEL_FALLBACK}"
                    fi
                fi
            fi
        fi
    fi

    if [ "${AGENT_OK}" = "1" ] && [ -n "${NEW}" ]; then
        SIGNALS=$((SIGNALS + NEW))
        OK=$((OK + 1))
        echo "[collect_all_actors] ✓ ${slug} — ${NEW} new signals (model=${USED_MODEL})"
    else
        FAIL=$((FAIL + 1))
        echo "[collect_all_actors] ✗ ${slug} — agent errored or returned no parseable signals (see ${LOGDIR}/${slug}.stderr.txt)"
    fi
done < "${ACTOR_LIST}"

# ── close the run row ────────────────────────────────────────────────────
# v0.4.26a: error message points at the per-actor *.stderr.txt files
# instead of persist.log. persist.log is only written when at least one
# actor's agent call succeeded enough to invoke the persister; when ALL
# actors fail at the `hermes chat` step, persist.log never exists and the
# old message ("see .../persist.log") sent operators looking at a file
# that's not there. The .stderr.txt files are always present (created by
# shell redirection at line ~190) so they're the right thing to point at.
if [ "${FAIL}" -eq 0 ]; then
    STATUS=ok
    ERR_MSG=""
else
    STATUS=error
    ERR_MSG="${FAIL} of ${N} actors failed (see ${LOGDIR}/*.stderr.txt for per-actor diagnostics)"
fi
python3 "${PERSIST}" --close-run --run-id "${RUN_ID}" --status "${STATUS}" \
    ${ERR_MSG:+--error-message "${ERR_MSG}"} >/dev/null
RUN_CLOSED=1
trap - EXIT INT TERM

echo ""
echo "[collect_all_actors] DONE  run=${RUN_ID}  actors=${N}  ok=${OK}  fail=${FAIL}  signals=${SIGNALS}"
echo "[collect_all_actors] full logs: ${LOGDIR}"

exit 0
