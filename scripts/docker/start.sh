#!/usr/bin/env bash
# =============================================================================
# docker/start.sh — Khởi động VietCropDoctor local development stack
#
# Usage:
#   ./scripts/docker/start.sh              # Khởi động tất cả service
#   ./scripts/docker/start.sh --no-browser # Không mở browser
#   ./scripts/docker/start.sh --infra-only # Chỉ khởi động infrastructure
#
# Yêu cầu: Docker Desktop (hoặc Docker Engine + Compose plugin)
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

COMPOSE="docker compose"
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-300}
OLLAMA_MODEL=${OLLAMA_MODEL:-qwen2.5:7b}
OPEN_BROWSER=true
INFRA_ONLY=false

for arg in "$@"; do
  case $arg in
    --no-browser)  OPEN_BROWSER=false ;;
    --infra-only)  INFRA_ONLY=true ;;
    --help|-h)
      echo "Usage: $0 [--no-browser] [--infra-only]"
      exit 0
      ;;
    *) warn "Unknown argument: $arg" ;;
  esac
done

REQUIRED_PORTS=(8000 8001 8002 8004 8005 8006 9092 6333 6379 5432 8123 11434)

echo ""
echo -e "${BOLD}━━━ VietCropDoctor — Start ━━━${NC}"
echo ""
info "Step 1/9: Checking prerequisites…"

command -v docker >/dev/null 2>&1 || die "Docker not found. Install Docker Desktop."
docker info >/dev/null 2>&1 || die "Docker daemon is not running. Please start Docker Desktop."
success "Docker is running ($(docker version --format '{{.Server.Version}}' 2>/dev/null || echo 'unknown'))"

docker compose version >/dev/null 2>&1 || die "Docker Compose plugin not found. Update Docker Desktop."
success "Docker Compose: $(docker compose version --short 2>/dev/null || echo 'ok')"

if command -v df >/dev/null 2>&1; then
  FREE_KB=$(df -k "${PROJECT_ROOT}" | awk 'NR==2{print $4}')
  FREE_GB=$(( FREE_KB / 1024 / 1024 ))
  [[ $FREE_GB -lt 10 ]] && warn "Only ${FREE_GB}GB free. Recommend 10GB+ for models." || success "Disk: ${FREE_GB}GB free"
fi

CONFLICT=false
for port in "${REQUIRED_PORTS[@]}"; do
  if lsof -Pi ":${port}" -sTCP:LISTEN -t >/dev/null 2>&1 || \
     ss -tlnp 2>/dev/null | grep -q ":${port} "; then
    warn "Port ${port} is already in use"
    CONFLICT=true
  fi
done
[[ "$CONFLICT" == "false" ]] && success "No port conflicts detected"

info "Step 2/9: Checking .env file…"
if [[ ! -f ".env" ]]; then
  if [[ -f ".env.example" ]]; then
    cp ".env.example" ".env"
    success "Copied .env.example → .env (đổi JWT_SECRET, POSTGRES_PASSWORD trước khi deploy)"
  else
    warn ".env not found. Services will use built-in defaults."
  fi
else
  success ".env file exists"
fi

info "Step 3/9: Creating data directories…"
DATA_DIRS=(
  backend/data/qdrant
  backend/data/ollama
  backend/data/mlflow/artifacts
  backend/data/mlflow
  backend/data/minio
  backend/data/airflow
  backend/data/training
  backend/data/models
  backend/logs
)
for dir in "${DATA_DIRS[@]}"; do
  mkdir -p "${dir}"
done
success "Data directories ready"

info "Step 4/9: Starting infrastructure (Kafka, Qdrant, Redis, PostgreSQL, ClickHouse, Ollama)…"
INFRA_SERVICES="zookeeper kafka qdrant redis postgres clickhouse ollama"
$COMPOSE up -d $INFRA_SERVICES

_wait_healthy() {
  local service="$1"
  local timeout="${2:-$HEALTH_TIMEOUT}"
  local elapsed=0
  local interval=5
  while [[ $elapsed -lt $timeout ]]; do
    status=$($COMPOSE ps --status=running "$service" 2>/dev/null | grep -c "$service" || true)
    health=$(docker inspect "vcd-${service}" --format='{{.State.Health.Status}}' 2>/dev/null || echo "none")
    if [[ "$health" == "healthy" ]] || { [[ "$health" == "none" ]] && [[ "$status" -gt 0 ]]; }; then
      return 0
    fi
    sleep $interval
    elapsed=$((elapsed + interval))
    echo -ne "\r  Waiting for ${service} (${elapsed}s)…   "
  done
  echo ""
  return 1
}

for svc in zookeeper kafka qdrant redis; do
  echo -ne "  Waiting for ${svc}…"
  if _wait_healthy "$svc" 120; then
    echo -e "\r  ${GREEN}✓${NC} ${svc} healthy                    "
  else
    echo ""
    die "${svc} did not become healthy within 120s. Check: $COMPOSE logs ${svc}"
  fi
done

for svc in postgres clickhouse; do
  echo -ne "  Waiting for ${svc}…"
  if _wait_healthy "$svc" 60; then
    echo -e "\r  ${GREEN}✓${NC} ${svc} healthy                    "
  else
    echo -e "\r  ${YELLOW}⚠${NC} ${svc} may not be ready (continuing)"
  fi
done

echo -ne "  Waiting for ollama…"
if _wait_healthy "ollama" 60; then
  echo -e "\r  ${GREEN}✓${NC} ollama healthy                    "
else
  echo -e "\r  ${YELLOW}⚠${NC} ollama not ready (continuing)"
fi

info "Step 5/9: Ensuring Ollama model is available (${OLLAMA_MODEL})…"
if docker exec vcd-ollama ollama list 2>/dev/null | grep -q "${OLLAMA_MODEL%%:*}"; then
  success "Model ${OLLAMA_MODEL} already present"
else
  info "Pulling ${OLLAMA_MODEL} (lần đầu mất 10–30 phút)…"
  docker exec vcd-ollama ollama pull "${OLLAMA_MODEL}" && \
    success "Model ${OLLAMA_MODEL} pulled" || \
    warn "Failed to pull model — orchestrator may be degraded"
fi

if [[ "$INFRA_ONLY" == "false" ]]; then
  info "Step 6/9: Starting monitoring stack (Prometheus, Grafana)…"
  $COMPOSE up -d prometheus grafana
  success "Monitoring stack started"
else
  info "Step 6/9: Skipping monitoring (--infra-only)"
fi

if [[ "$INFRA_ONLY" == "false" ]]; then
  info "Step 7/9: Starting application services…"
  $COMPOSE up -d vision-ai rag-engine analytics auth

  for svc in vision-ai rag-engine analytics auth; do
    echo -ne "  Waiting for ${svc}…"
    if _wait_healthy "$svc" 120; then
      echo -e "\r  ${GREEN}✓${NC} ${svc} healthy                    "
    else
      echo -e "\r  ${YELLOW}⚠${NC} ${svc} not ready (check: $COMPOSE logs ${svc})"
    fi
  done

  $COMPOSE up -d orchestrator
  echo -ne "  Waiting for orchestrator…"
  if _wait_healthy "orchestrator" 60; then
    echo -e "\r  ${GREEN}✓${NC} orchestrator healthy              "
  else
    echo -e "\r  ${YELLOW}⚠${NC} orchestrator not ready            "
  fi
else
  info "Step 7/9: Skipping app services (--infra-only)"
fi

if [[ "$INFRA_ONLY" == "false" ]]; then
  info "Step 8/9: Starting gateway…"
  $COMPOSE up -d gateway
  echo -ne "  Waiting for gateway…"
  if _wait_healthy "gateway" 30; then
    echo -e "\r  ${GREEN}✓${NC} gateway healthy                   "
  else
    echo -e "\r  ${YELLOW}⚠${NC} gateway not ready                 "
  fi
else
  info "Step 8/9: Skipping gateway (--infra-only)"
fi

info "Step 9/9: Starting optional services (MLflow, Airflow, Kafka UI, MinIO)…"
$COMPOSE up -d mlflow airflow kafka-ui minio 2>/dev/null || true
success "Optional services started"

echo ""
echo -e "${BOLD}━━━ Service Summary ━━━${NC}"
echo ""

_check_url() {
  local url="$1"
  local status
  status=$(curl -sf --max-time 3 "${url}" -o /dev/null -w "%{http_code}" 2>/dev/null || echo "000")
  if [[ "$status" =~ ^2 ]]; then echo -e "${GREEN}✅${NC}"
  else echo -e "${RED}❌${NC} (HTTP ${status})"; fi
}

printf "  %-22s %-35s %s\n" "Service" "URL" "Status"
printf "  %-22s %-35s %s\n" "-------" "---" "------"
printf "  %-22s %-35s %s\n" "Gateway"       "http://localhost:8000"  "$(_check_url http://localhost:8000/health)"
printf "  %-22s %-35s %s\n" "Vision-AI"     "http://localhost:8001"  "$(_check_url http://localhost:8001/health)"
printf "  %-22s %-35s %s\n" "RAG Engine"    "http://localhost:8002"  "$(_check_url http://localhost:8002/health)"
printf "  %-22s %-35s %s\n" "Analytics"     "http://localhost:8004"  "$(_check_url http://localhost:8004/health)"
printf "  %-22s %-35s %s\n" "Auth"          "http://localhost:8005"  "$(_check_url http://localhost:8005/health)"
printf "  %-22s %-35s %s\n" "Orchestrator"  "http://localhost:8006"  "$(_check_url http://localhost:8006/health)"
printf "  %-22s %-35s %s\n" "MLflow"        "http://localhost:5000"  "$(_check_url http://localhost:5000/health)"
printf "  %-22s %-35s %s\n" "Kafka UI"      "http://localhost:8080"  "$(_check_url http://localhost:8080)"
printf "  %-22s %-35s %s\n" "MinIO Console" "http://localhost:9001"  "$(_check_url http://localhost:9001)"
printf "  %-22s %-35s %s\n" "Prometheus"    "http://localhost:9090"  "$(_check_url http://localhost:9090/-/healthy)"
printf "  %-22s %-35s %s\n" "Grafana"       "http://localhost:3001"  "$(_check_url http://localhost:3001/api/health)"
printf "  %-22s %-35s %s\n" "Airflow"       "http://localhost:8090"  "$(_check_url http://localhost:8090/health)"
echo ""

if [[ "$OPEN_BROWSER" == "true" ]]; then
  echo -e "  Opening ${CYAN}http://localhost:8000${NC} …"
  case "$(uname -s)" in
    Darwin) open "http://localhost:8000" ;;
    Linux)  xdg-open "http://localhost:8000" 2>/dev/null || true ;;
  esac
fi

echo ""
echo -e "${GREEN}${BOLD}VietCropDoctor is ready!${NC}"
echo -e "  App:      http://localhost:8000"
echo -e "  API docs: http://localhost:8001/docs"
echo -e "  Grafana:  http://localhost:3001  (admin / admin)"
echo -e "  MLflow:   http://localhost:5000"
echo ""
