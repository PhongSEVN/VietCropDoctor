#!/usr/bin/env bash
# =============================================================================
# ml/seed-models.sh — Download model weights vào MinIO / local model cache
#
# Usage:
#   ./scripts/ml/seed-models.sh                    # Download tất cả model
#   ./scripts/ml/seed-models.sh --model mobilenet  # Download một model
#   ./scripts/ml/seed-models.sh --list             # Liệt kê model khả dụng
#
# Model weights lưu tại: backend/data/models/
# MinIO bucket: vcd-uploads/models/
#
# Yêu cầu:
#   - MLflow đang chạy (docker compose up -d mlflow)
#   - mc (MinIO Client) nếu muốn đồng bộ lên MinIO
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

MODEL_DIR="${PROJECT_ROOT}/backend/data/models"
MINIO_ALIAS="vcd-local"
MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9002}"
MINIO_ACCESS="${MINIO_ROOT_USER:-minioadmin}"
MINIO_SECRET="${MINIO_ROOT_PASSWORD:-minioadmin}"
BUCKET="${MINIO_BUCKET_UPLOADS:-vcd-uploads}"

MODELS=(
  "efficientnet_b0"
  "mobilenetv3_large"
  "resnet50"
  "vit_base"
  "yolov11"
)

MODEL_FILTER=""
LIST_ONLY=false

for arg in "$@"; do
  case $arg in
    --model)  shift; MODEL_FILTER="$1" ;;
    --list)   LIST_ONLY=true ;;
    --help|-h)
      echo "Usage: $0 [--model <name>] [--list]"
      echo "  --model <name>  Download only this model"
      echo "  --list          List available models and exit"
      echo ""
      echo "Available models: ${MODELS[*]}"
      exit 0
      ;;
  esac
done

echo ""
echo -e "${BOLD}━━━ VietCropDoctor — Seed Models ━━━${NC}"
echo ""

if [[ "$LIST_ONLY" == "true" ]]; then
  info "Available models:"
  for m in "${MODELS[@]}"; do echo "  - ${m}"; done
  echo ""
  exit 0
fi

mkdir -p "${MODEL_DIR}"

info "Checking MLflow…"
if curl -sf http://localhost:5000/health >/dev/null 2>&1; then
  success "MLflow reachable at http://localhost:5000"
  USE_MLFLOW=true
else
  warn "MLflow not running — will use placeholder weights"
  USE_MLFLOW=false
fi

_download_model() {
  local name="$1"
  local dest="${MODEL_DIR}/${name}"
  mkdir -p "${dest}"

  if [[ "$USE_MLFLOW" == "true" ]]; then
    info "Fetching ${name} best checkpoint from MLflow…"
    docker exec vcd-mlflow python - <<PYEOF 2>/dev/null || warn "MLflow fetch failed for ${name}"
import mlflow
mlflow.set_tracking_uri("http://localhost:5000")
client = mlflow.MlflowClient()
exp = client.get_experiment_by_name("vietcropdoctor-classification")
if exp:
    runs = client.search_runs(exp.experiment_id, filter_string=f"tags.model_name = '{name}'", order_by=["start_time DESC"], max_results=1)
    if runs:
        run_id = runs[0].info.run_id
        mlflow.artifacts.download_artifacts(run_id=run_id, artifact_path="model", dst_path="${dest}")
        print(f"Downloaded {name} to ${dest}")
    else:
        print(f"No runs found for {name}")
PYEOF
  else
    info "Creating placeholder for ${name}…"
    echo "placeholder — replace with actual weights" > "${dest}/README.txt"
  fi
  success "${name} → ${dest}"
}

if [[ -n "$MODEL_FILTER" ]]; then
  _download_model "$MODEL_FILTER"
else
  for model in "${MODELS[@]}"; do
    _download_model "$model"
  done
fi

if command -v mc >/dev/null 2>&1; then
  info "Syncing models to MinIO (${MINIO_ENDPOINT})…"
  mc alias set "${MINIO_ALIAS}" "${MINIO_ENDPOINT}" "${MINIO_ACCESS}" "${MINIO_SECRET}" >/dev/null 2>&1 || \
    warn "Could not configure mc alias — skipping MinIO sync"
  mc cp --recursive "${MODEL_DIR}/" "${MINIO_ALIAS}/${BUCKET}/models/" 2>/dev/null && \
    success "Models synced to MinIO bucket ${BUCKET}/models/" || \
    warn "MinIO sync failed — models available locally at ${MODEL_DIR}"
else
  info "mc (MinIO Client) not installed — models saved locally at ${MODEL_DIR}"
fi

echo ""
success "Model seeding complete."
echo ""
info "Model directory: ${MODEL_DIR}"
info "Update MODEL_PATH in .env to point to the desired checkpoint."
echo ""
