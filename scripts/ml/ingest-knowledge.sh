#!/usr/bin/env bash
# =============================================================================
# ml/ingest-knowledge.sh — Chạy pipeline ingest tài liệu vào Qdrant
#
# Usage:
#   ./scripts/ml/ingest-knowledge.sh                  # Ingest tất cả cây trồng
#   ./scripts/ml/ingest-knowledge.sh --crop lua       # Ingest từng cây trồng
#   ./scripts/ml/ingest-knowledge.sh --crop ca-phe
#   ./scripts/ml/ingest-knowledge.sh --rebuild        # Xoá collection cũ, ingest lại
#
# Yêu cầu:
#   - Qdrant đang chạy  (docker compose up -d qdrant)
#   - RAG engine đang chạy  (docker compose up -d rag-engine)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

CROP=""
REBUILD=false

for arg in "$@"; do
  case $arg in
    --crop)       shift; CROP="$1" ;;
    --rebuild)    REBUILD=true ;;
    --help|-h)
      echo "Usage: $0 [--crop <name>] [--rebuild]"
      echo "  --crop <name>  Ingest only this crop (lua, ca-phe, mia, ngo)"
      echo "  --rebuild      Drop existing collection and re-ingest from scratch"
      exit 0
      ;;
  esac
done

echo ""
echo -e "${BOLD}━━━ VietCropDoctor — Knowledge Ingestion ━━━${NC}"
echo ""

info "Checking Qdrant…"
curl -sf http://localhost:6333/healthz >/dev/null 2>&1 || \
  die "Qdrant is not reachable at http://localhost:6333. Run: docker compose up -d qdrant"
success "Qdrant is reachable"

# Ingestion is performed via the RAG engine HTTP API (POST /ingest, /reindex).
# These endpoints run the live pipeline (sentence-transformers, local) and
# rebuild the BM25 index — so the engine must be up.
RAG_URL="${RAG_ENGINE_URL:-http://localhost:8002}"
# Path INSIDE the rag-engine container (the repo is mounted at /service, and the
# default knowledge dir is rag/knowledge → /service/rag/knowledge).
KNOWLEDGE_DIR="rag/knowledge"

info "Checking RAG engine…"
curl -sf "${RAG_URL}/health" >/dev/null 2>&1 || \
  die "RAG engine không chạy tại ${RAG_URL}. Run: docker compose up -d rag-engine"
success "RAG engine is reachable"

# Map crop slug → thư mục con (tên có dấu) trong rag/knowledge
crop_dir() {
  case "$1" in
    lua)    echo "${KNOWLEDGE_DIR}/lúa" ;;
    ca-phe) echo "${KNOWLEDGE_DIR}/cà phê" ;;
    mia)    echo "${KNOWLEDGE_DIR}/mía" ;;
    ngo)    echo "${KNOWLEDGE_DIR}/ngô" ;;
    *)      die "Crop không hợp lệ '$1' (hợp lệ: lua, ca-phe, mia, ngo)" ;;
  esac
}

if [[ "$REBUILD" == "true" ]]; then
  info "Rebuild: xoá collection và ingest lại toàn bộ ${KNOWLEDGE_DIR}…"
  curl -fsS -X POST "${RAG_URL}/reindex" \
    || die "Reindex thất bại (HTTP)."
elif [[ -n "$CROP" ]]; then
  DIR="$(crop_dir "$CROP")"
  info "Ingesting crop '${CROP}' từ '${DIR}'…"
  curl -fsS -X POST "${RAG_URL}/ingest" \
    -H 'Content-Type: application/json' \
    -d "$(printf '{"directory": "%s", "recreate_collection": false}' "$DIR")" \
    || die "Ingest crop thất bại (HTTP)."
else
  info "Ingesting toàn bộ '${KNOWLEDGE_DIR}'…"
  curl -fsS -X POST "${RAG_URL}/ingest" \
    -H 'Content-Type: application/json' \
    -d "$(printf '{"directory": "%s", "recreate_collection": false}' "$KNOWLEDGE_DIR")" \
    || die "Ingest thất bại (HTTP)."
fi
echo ""

success "Knowledge ingestion complete."
echo ""
info "Verify: curl http://localhost:6333/collections"
echo ""
