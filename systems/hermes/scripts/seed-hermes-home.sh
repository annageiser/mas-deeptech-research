#!/command/with-contenv sh
# Seed $HERMES_HOME with our Swiss-quantum skill + cron-mode config.
# Runs as cont-init.d/03- AFTER the upstream stage2 hook (01-hermes-setup)
# but BEFORE s6 starts any services.
#
# IMPORTANT — v0.4.9: ALWAYS overwrite skill + config.
# Until v0.4.8 we skipped if the destination existed, to preserve user
# edits. But upstream's 01-hermes-setup hook drops its full 62 KB
# example config (with default model = anthropic/claude-opus-4.6 PAID)
# into /opt/data/config.yaml BEFORE this hook runs. Our skip-if-exists
# logic then left the example in place, the cron loop never ran with our
# free-tier config, and every actor call hit OpenRouter 402. See
# docs/iterations/v0.4.9-seed-hook-always-overwrite.md for the full trail.
#
# Trade-off accepted: if you customize $HERMES_HOME/config.yaml in the
# volume by hand, your edits will be lost on the next container start.
# The supported customization path is editing
# systems/hermes/config/cli-config.yaml in the repo + image rebuild.
set -eu

HERMES_HOME="${HERMES_HOME:-/opt/data}"
SRC=/opt/swiss-quantum

mkdir -p "${HERMES_HOME}/skills" "${HERMES_HOME}/state"

# Skill — always (over)write from the image. The skill is part of the
# artefact, not user state.
SKILL_DST="${HERMES_HOME}/skills/collect-swiss-quantum-signals"
rm -rf "${SKILL_DST}"
cp -r "${SRC}/skills/collect-swiss-quantum-signals" "${SKILL_DST}"
echo "[seed-hermes-home] installed skill: collect-swiss-quantum-signals"

# Config — always (over)write from the image. Replaces upstream's
# 62 KB example config that 01-hermes-setup just dropped here.
CFG_DST="${HERMES_HOME}/config.yaml"
cp "${SRC}/config.yaml" "${CFG_DST}"
echo "[seed-hermes-home] installed cron-mode config.yaml ($(wc -c < "${CFG_DST}") bytes)"

# Fix ownership — stage2-hook may have remapped HERMES_UID.
chown -R hermes:hermes "${HERMES_HOME}/skills" "${HERMES_HOME}/state" "${CFG_DST}" 2>/dev/null || true

echo "[seed-hermes-home] done — HERMES_HOME=${HERMES_HOME}"
