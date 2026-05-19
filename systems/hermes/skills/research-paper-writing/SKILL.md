---
name: research-paper-writing
description: Compose the short per-actor markdown brief that ends each run.
version: 0.1.0
platforms: [linux, macos]
metadata:
  hermes:
    tags: [writing, swiss-quantum]
    category: synthesis
---

# When to use

Use exactly once per actor, as the final tool call: invoke `finish_actor`
with the markdown brief as `summary_md`.

# Procedure

The brief is read by a research supervisor scanning many actors in a row.
Keep it ruthlessly short:

```
**<Actor Name>**
- <dimension>: <one-line takeaway with [source](url)>
- <dimension>: <one-line takeaway with [source](url)>

_Notable this run: <one sentence on the single most important signal, or
"nothing of note" if the registered signals are routine>._
```

Rules:
- 2–5 bullets maximum.
- Each bullet cites a signal you registered this run.
- Use `[source](url)` markdown links pointing to the actual evidence page.
- Do not invent signals here — only mention ones that exist in your
  `register_signal` history.

# Pitfalls

- LLMs love to inflate ("strong commitment to innovation"). Strip adjectives.
- If you registered zero signals, the brief should still say so explicitly —
  don't fabricate.

# Verification

The brief appears in the audit folder's `brief.md`. A supervisor should be
able to map every bullet to a row in `signals` via the source URL.
