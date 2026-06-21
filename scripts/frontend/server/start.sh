#!/usr/bin/env bash
# frontend/server/start.sh — Build React production bundle và deploy lên Nginx gateway
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "${SCRIPT_DIR}/../../../client/web" && pwd)"

echo "=== VietCropDoctor — Frontend Production Build ==="
echo ""

cd "${WEB_DIR}"

if [[ ! -d "node_modules" ]]; then
    echo "[INFO] Cài dependencies..."
    npm install
fi

echo "[INFO] Build production bundle..."
npm run build
echo "[OK]   Build hoàn tất: ${WEB_DIR}/dist"
echo ""

if docker inspect vcd-gateway --format='{{.State.Running}}' 2>/dev/null | grep -q true; then
    echo "[INFO] Copy dist vào gateway container..."
    docker cp "${WEB_DIR}/dist/." vcd-gateway:/usr/share/nginx/html/
    echo "[INFO] Reload Nginx..."
    docker exec vcd-gateway nginx -s reload
    echo "[OK]   Gateway đã được cập nhật."
else
    echo "[WARN] Container vcd-gateway không chạy."
    echo "       Build đã xong tại ${WEB_DIR}/dist"
    echo "       Chạy: docker compose up -d gateway"
fi
