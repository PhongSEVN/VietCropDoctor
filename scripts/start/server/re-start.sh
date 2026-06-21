#!/usr/bin/env bash
# start/server/re-start.sh — Restart một hoặc nhiều service trên server (Linux)
#
# Usage:
#   ./scripts/start/server/re-start.sh                  Restart toàn bộ stack
#   ./scripts/start/server/re-start.sh gateway auth     Chỉ restart các service chỉ định
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

cd "${PROJECT_ROOT}"

if [[ $# -gt 0 ]]; then
    echo "=== Restart: $* ==="
    docker compose restart "$@"
    echo "[OK]   Restarted: $*"
else
    echo "=== Restart toàn bộ stack ==="
    docker compose restart
    echo "[OK]   Stack restarted."
fi
