#!/usr/bin/env bash
# Container C (Reports) entrypoint.
#
#   daily --system masfactory   : produce today's per-system report
#   daily --system hermes
#   weekly --system masfactory  : produce this week's per-system report
#   weekly --system hermes
#   weekly-thesis               : produce this week's thesis-progress report
#   build-check                 : verify imports + prompts (used during build)
#   shell                       : bash for ad-hoc debugging

set -euo pipefail

cmd="${1:-build-check}"
shift || true

case "$cmd" in
  daily|weekly|weekly-thesis|build-check)
    exec python -m reports_system.runner "$cmd" "$@"
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    exec python -m reports_system.runner "$cmd" "$@"
    ;;
esac
