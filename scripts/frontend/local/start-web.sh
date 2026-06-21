#!/usr/bin/env bash
# frontend/local/start-web.sh — Khởi động React dev server (Linux/macOS)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(cd "${SCRIPT_DIR}/../../../client/web" && pwd)"

cd "${WEB_DIR}"

if [[ ! -d "node_modules" ]]; then
    echo "[INFO] node_modules chưa có — chạy npm install..."
    npm install
fi

echo "[INFO] Khởi động React dev server..."
echo "[INFO] URL: http://localhost:5173"
echo ""
npm run dev
