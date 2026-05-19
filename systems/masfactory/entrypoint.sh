#!/usr/bin/env bash
# Container A entrypoint.
#
#   run-once     : execute the MASFactory graph once and exit (cron mode).
#   build-check  : smoke-test the graph without env vars (used during image build).
#   shell        : drop into bash for ad-hoc debugging on the VPS.
#
# Any unrecognised argv is forwarded verbatim to `python -m masfactory_system.runner`.

set -euo pipefail

cmd="${1:-run-once}"
shift || true

case "$cmd" in
  run-once)
    exec python -m masfactory_system.runner run-once "$@"
    ;;
  build-check)
    exec python -m masfactory_system.runner build-check
    ;;
  shell)
    exec /bin/bash "$@"
    ;;
  *)
    exec python -m masfactory_system.runner "$cmd" "$@"
    ;;
esac
