#!/usr/bin/env bash
# Container B (Hermes) entrypoint.
#
#   run-once     : execute one batch and exit (cron mode).
#   build-check  : verify package + skills parse (used during image build).
#   shell        : bash for ad-hoc debugging on the VPS.
#
# Any unrecognised argv is forwarded to `python -m hermes_system.runner`.

set -euo pipefail

cmd="${1:-run-once}"
shift || true

case "$cmd" in
  run-once)
    exec python -m hermes_system.runner run-once "$@"
    ;;
  build-check)
    exec python -m hermes_system.runner build-check
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    exec python -m hermes_system.runner "$cmd" "$@"
    ;;
esac
