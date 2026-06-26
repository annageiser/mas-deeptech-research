# Deploy Anleitung — v0.4.38 + v0.4.39 + v0.4.40

**Datum:** 2026-06-26
**Wer:** Anna
**Geschätzte Dauer:** ~25 Minuten total

---

## Was ist neu

| Version | Was | Wo angeschaut |
|---|---|---|
| **v0.4.38** | Beide MAS-Systeme auf Nemotron 3 Ultra 550B (gratis) | [PR #13](https://github.com/annageiser/mas-deeptech-research/pull/13) · [Doc](docs/iterations/v0.4.38-nemotron-3-ultra-migration.md) |
| **v0.4.39** | QualCoder-Workflow für 50 Gold-Signale | [PR #14](https://github.com/annageiser/mas-deeptech-research/pull/14) · [Doc](docs/iterations/v0.4.39-qualitative-research-module.md) |
| **v0.4.40** | Knowledge-Graph erweitert + Code-Memory Dev-Tool | [PR #15](https://github.com/annageiser/mas-deeptech-research/pull/15) · [Doc](docs/iterations/v0.4.40-codebase-memory-and-knowledge-graph.md) |

---

## Schritt 1 — PRs mergen (auf GitHub)

Reihenfolge egal — keine Konflikte zwischen den drei.

```
PR #13: v0.4.38  → Review → Merge
PR #14: v0.4.39  → Review → Merge
PR #15: v0.4.40  → Review → Merge
```

Wenn die CI grün ist, kannst du auch alle drei direkt mergen.

---

## Schritt 2 — Auf der VPS pullen + rebuilden

SSH auf die VPS:

```bash
ssh root@<deine-vps-ip>
cd /opt/mas-deeptech-research

# Pull
git pull origin main

# Rebuild alle relevanten Container (~5 Min)
docker compose build masfactory hermes reports api web

# Restart die always-on Services
docker compose up -d api web caddy
```

---

## Schritt 3 — `.env` auf VPS aktualisieren

Falls du Nemotron 3 Ultra nutzen willst (sonst bleibt der Default greifen):

```bash
# /opt/mas-deeptech-research/.env editieren
nano .env
```

Hinzufügen oder ändern:

```bash
MASF_MODEL_MAIN=nvidia/nemotron-3-ultra-550b-a55b:free
MASF_MODEL_FALLBACK=qwen/qwen3-next-80b-a3b-instruct:free
HERMES_MODEL=nvidia/nemotron-3-ultra-550b-a55b:free
HERMES_MODEL_FALLBACK=qwen/qwen3-next-80b-a3b-instruct:free
MASF_REASONING_EXCLUDE=1
HERMES_REASONING_EXCLUDE=1
```

Rein neu zu setzen ist auch ok — die alten `MASF_MODEL_MAIN=qwen/...` Zeilen einfach überschreiben.

---

## Schritt 4 — Smoke-Tests (kurz)

### v0.4.38 — Test ob Nemotron läuft

```bash
# 3 Aktoren, 60 Tage Lookback (~5 Min)
docker compose run --rm \
    -e HERMES_LIMIT_ACTORS=3 \
    -e HERMES_LOOKBACK_DAYS=60 \
    hermes
```

**Erwarte:** Zeilen wie
```
[collect_all_actors] ✓ eth-zurich — 3 new signals (model=nvidia/nemotron-3-ultra-550b-a55b:free)
```

Wenn du `↻ retry with fallback` siehst: primary hatte ein Problem mit dem Aktor, fallback hat's gefangen. Normal.

### v0.4.40 — Test ob neue Knowledge-Graph-Layer da sind

Im Browser:
```
https://mas-deeptech-research.cloud/graph?days=28&taxonomy=1
```

**Erwarte:** Innerster Ring mit 4 farbigen Knoten (Legitimacy, Customer co-creation, Community ecosystem, Future trajectory) + gestrichelte Linien zu den Dimensionen.

```
https://mas-deeptech-research.cloud/graph?days=28&semantic=1
```

**Erwarte:** Lila gestrichelte Linien zwischen Aktoren — aber nur wenn Embeddings populated sind. Wenn nicht, siehst du keine lila Linien — das ist kein Bug.

### v0.4.39 — QDA-Export testen

```bash
docker compose run --rm \
    -v /tmp/qda:/tmp/qda \
    reports python -m eval_app.qda export \
        --out /tmp/qda/test.qdpx \
        --window-days 28 \
        --sample-size 5
```

**Erwarte:**
```
[qda export] wrote /tmp/qda/test.qdpx  (n=5, seed-log /tmp/qda/test.seed.txt)
[qda export] per-cell counts:
    ...
```

---

## Schritt 5 — Code-Memory-MCP installieren (Anna's MacBook, einmalig)

Optional, aber nützlich für deinen Editor:

```bash
# Lokal auf dem MacBook (NICHT auf VPS!)
curl -fsSL https://raw.githubusercontent.com/DeusData/codebase-memory-mcp/main/install.sh | bash

# Verifizieren
codebase-memory-mcp --version

# Index bauen (im Repo-Root)
cd ~/mas-deeptech-research
codebase-memory-mcp index . --cache-dir .codebase-memory
```

Dann Claude Code (oder Cursor) neu starten. Im Claude-Code-Session: `/mcp` zeigt jetzt `codebase-memory` mit 14 Tools.

---

## Was du JETZT machen kannst

### 1. Gold-Set codieren (P0-Blocker auflösen!)

```bash
# Auf VPS — Sampled die 50 Gold-Signale
docker compose run --rm \
    -v /tmp/qda:/tmp/qda \
    reports python -m eval_app.qda export \
        --out /tmp/qda/gold-2026-06-26.qdpx \
        --window-days 28 \
        --sample-size 50 \
        --seed 42

# Auf MacBook — Datei runterziehen
scp root@<vps>:/tmp/qda/gold-2026-06-26.qdpx ~/Desktop/

# In QualCoder öffnen
qualcoder  # GUI → File → Import REFI-QDA project
```

Dann codieren (50 × ~3 Min = ~2.5h für komplettes Set).

### 2. Knowledge-Graph mit neuen Layern in der Thesis zeigen

`/graph?days=28&taxonomy=1` als Screenshot für **§2.1.5 "Ideal reference architecture"** (Backlog P1 #8).

### 3. Phoenix-Trace optional aktivieren falls du V&V-Replay willst

(unverändert seit v0.4.25 — siehe `.env.example` Phoenix Block)

---

## Wenn was schiefgeht

| Problem | Quick-Fix |
|---|---|
| Nemotron returnt nichts | Check OpenRouter Quota; oder `HERMES_MODEL=qwen/qwen3-next-80b-a3b-instruct:free` setzen → Rollback ohne Code-Änderung |
| `/graph?taxonomy=1` zeigt nur Standard-Layout | Cache; in `docker compose restart api web caddy` ausführen |
| QDA export bricht ab | Check Window-Days — wenn 28 Tage zu wenig Signale: `--window-days 90` |
| Code-Memory-MCP "tool unavailable" | Binary nicht auf `$PATH`; nochmal Install-Script |

---

## Status nach dem Deploy

✅ Beide MAS-Systeme auf Frontier-Modell (Nemotron 3 Ultra 550B)
✅ Gold-Set-Workflow ready → kannst direkt anfangen
✅ Knowledge-Graph mit Taxonomy + semantischer Layer
✅ Dev-Workflow mit Code-Memory MCP (optional)
✅ Alle Änderungen dokumentiert in `docs/iterations/v0.4.{38,39,40}-*.md`

Verbleibende P0-Blocker (CLEAN_BACKLOG_NO_1):
- 50-Zeilen Gold-Set hand-codieren — Tooling ist da, jetzt machbar
- AI-Declaration in Thesis-Docx
- §2.2.2 Iteration-Count fixen
- §3.4/§3.2/§4.1.3/§5.1 "free-tier-only" Widerspruch fixen
- Abstract + Preface + Listen
- Evaluation-Window schließen (2026-07-20)
