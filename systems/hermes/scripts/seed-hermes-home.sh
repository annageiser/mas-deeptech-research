#!/command/with-contenv sh
# Seed $HERMES_HOME with our Swiss-quantum skill + config on first boot.
# Runs as cont-init.d/03- AFTER the upstream stage2 hook (01-hermes-setup)
# has fixed up volume permissions but BEFORE s6 starts any services.
#
# Idempotent: only copies a file if it doesn't already exist, so user
# edits to the volume survive container restart and image rebuild.
set -eu

HERMES_HOME="${HERMES_HOME:-/opt/data}"
SRC=/opt/swiss-quantum

mkdir -p "${HERMES_HOME}/skills" "${HERMES_HOME}/state"

# Skill — overwrite ONLY if missing or older than the image-baked copy.
# This lets us ship skill updates via image bumps without manual reset.
SKILL_DST="${HERMES_HOME}/skills/collect-swiss-quantum-signals"
if [ ! -d "${SKILL_DST}" ] || [ "${SRC}/skills/collect-swiss-quantum-signals/SKILL.md" -nt "${SKILL_DST}/SKILL.md" ]; then
    cp -r "${SRC}/skills/collect-swiss-quantum-signals" "${SKILL_DST}"
    echo "[seed-hermes-home] installed/updated skill: collect-swiss-quantum-signals"
fi

# Config — copy only if missing. Users edit this; we don't clobber.
CFG_DST="${HERMES_HOME}/config.yaml"
if [ ! -f "${CFG_DST}" ]; then
    cp "${SRC}/config.yaml" "${CFG_DST}"
    echo "[seed-hermes-home] installed default config.yaml"
fi

# Fix ownership — stage2-hook may have remapped HERMES_UID.
chown -R hermes:hermes "${HERMES_HOME}/skills" "${HERMES_HOME}/state" "${CFG_DST}" 2>/dev/null || true

echo "[seed-hermes-home] done — HERMES_HOME=${HERMES_HOME}"
