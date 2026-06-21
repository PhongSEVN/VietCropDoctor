#!/usr/bin/env bash
# test/gateway/run.sh — Chạy gateway integration tests (Linux/macOS)
#
# Usage:
#   ./scripts/test/gateway/run.sh                    # Tất cả tests
#   ./scripts/test/gateway/run.sh test_rbac.py       # Chỉ RBAC
#   ./scripts/test/gateway/run.sh -k test_login      # Filter theo tên
#   GATEWAY_URL=http://staging:8000 ./scripts/test/gateway/run.sh
#
# Yêu cầu:
#   docker compose up -d postgres redis auth gateway
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR="$(cd "${SCRIPT_DIR}/../../../test system/gateway" && pwd)"

GATEWAY_URL="${GATEWAY_URL:-http://localhost:8000}"

echo "=== VietCropDoctor — Gateway Tests ==="
echo "  Gateway : ${GATEWAY_URL}"
echo "  Dir     : ${TEST_DIR}"
echo ""

cd "${TEST_DIR}"

if ! python3 -c "import pytest, requests" 2>/dev/null; then
    echo "[INFO] Cài test dependencies..."
    pip install -r requirements.txt
fi

GATEWAY_URL="${GATEWAY_URL}" pytest -v "$@"
