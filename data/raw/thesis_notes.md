# Thesis notes — Anna's running journal

Use this file to drop short notes the weekly thesis-progress report can
incorporate. The report reads the *whole file* every Sunday and weaves the
relevant bits into the progress narrative.

> Format is free-form. Date-stamped headers help the LLM scope to the
> current week. Old entries can stay — the report doesn't care.

## 2026-05-21

- Live deployment to Hostinger VPS srv1684595. Both systems running on
  daily cron (02:00 + 05:00 UTC). Three weekly reports scheduled for
  Sunday 08:00 UTC.
- First real-data run: System A 6 signals, System B 1. System B uses
  ~2.15× tokens for ~1/11 the yield. Need to discuss with supervisor
  whether this asymmetry is the comparison's main finding or whether
  System B's prompt protocol needs more rounds of tuning before fair
  measurement.
- Schema patch lesson: Supabase service_role doesn't auto-grant on new
  tables; added explicit GRANTs to schema.sql and a `calls` column to
  `token_usage`. Documented in docs/session_log.md.

## (next week here)
