#!/usr/bin/env bash
# frontend/server/restart-nginx.sh — Test config và reload Nginx gateway
set -euo pipefail

echo "=== Restart Nginx gateway ==="
echo ""

if ! docker inspect vcd-gateway --format='{{.State.Running}}' 2>/dev/null | grep -q true; then
    echo "[ERROR] Container vcd-gateway không chạy."
    echo "        Chạy: docker compose up -d gateway"
    exit 1
fi

echo "[INFO] Test config Nginx..."
docker exec vcd-gateway nginx -t
echo "[INFO] Reload Nginx..."
docker exec vcd-gateway nginx -s reload
echo "[OK]   Nginx reloaded thành công."
