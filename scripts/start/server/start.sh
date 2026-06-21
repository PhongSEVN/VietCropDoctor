#!/usr/bin/env bash
# start/server/start.sh — Khởi động VietCropDoctor trên server (Linux)
#
# Dành cho môi trường server/staging/prod.
# Build frontend, pull images mới nhất, restart stack.
#
# Usage:
#   ./scripts/start/server/start.sh
#   ./scripts/start/server/start.sh --no-build   Bỏ qua bước build frontend
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

BUILD_FRONTEND=true
for arg in "$@"; do
  [[ "$arg" == "--no-build" ]] && BUILD_FRONTEND=false
done

echo "=== VietCropDoctor — Server Start ==="
echo ""

cd "${PROJECT_ROOT}"

echo "[INFO] Pulling latest images..."
docker compose pull

if [[ "$BUILD_FRONTEND" == "true" ]]; then
    echo "[INFO] Building frontend..."
    "${SCRIPT_DIR}/../../frontend/server/start.sh"
fi

echo "[INFO] Starting stack..."
docker compose up -d
echo "[OK]   Stack started."
echo "       App: http://localhost:8000"
