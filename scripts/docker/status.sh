#!/usr/bin/env bash
# =============================================================================
# docker/status.sh — Hiển thị trạng thái VietCropDoctor stack
#
# Usage:
#   ./scripts/docker/status.sh          # Full status report
#   ./scripts/docker/status.sh --short  # Container list only
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

SHORT=false
for arg in "$@"; do
  case $arg in
    --short)  SHORT=true ;;
    --help|-h)
      echo "Usage: $0 [--short]"
      exit 0
      ;;
    *) warn "Unknown argument: $arg" ;;
  esac
done

echo ""
echo -e "${BOLD}━━━ VietCropDoctor — Stack Status ━━━${NC}"
echo ""

# ── Container status ──────────────────────────────────────────────────────────
echo -e "${BOLD}Containers:${NC}"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || \
  docker compose ps 2>/dev/null

echo ""

if [[ "$SHORT" == "true" ]]; then
  exit 0
fi

# ── Resource usage ────────────────────────────────────────────────────────────
echo -e "${BOLD}Resource Usage (CPU / RAM):${NC}"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}" \
  $(docker compose ps -q 2>/dev/null) 2>/dev/null || \
  echo "  (no containers running)"

echo ""

# ── Health check results ──────────────────────────────────────────────────────
echo -e "${BOLD}Health Checks:${NC}"
echo ""

declare -A ENDPOINTS=(
  ["Gateway"]="http://localhost:8000/health"
  ["Vision-AI"]="http://localhost:8001/health"
  ["RAG Engine"]="http://localhost:8002/health"
  ["Analytics"]="http://localhost:8004/health"
  ["Auth"]="http://localhost:8005/health"
  ["Orchestrator"]="http://localhost:8006/health"
  ["MLflow"]="http://localhost:5000/health"
  ["Kafka UI"]="http://localhost:8080"
  ["MinIO"]="http://localhost:9001"
  ["Prometheus"]="http://localhost:9090/-/healthy"
  ["Grafana"]="http://localhost:3001/api/health"
  ["Airflow"]="http://localhost:8090/health"
  ["Qdrant"]="http://localhost:6333/healthz"
)

printf "  %-20s %-40s %-10s %s\n" "Service" "URL" "HTTP" "Latency"
printf "  %-20s %-40s %-10s %s\n" "-------" "---" "----" "-------"

for svc in "Gateway" "Vision-AI" "RAG Engine" "Analytics" "Auth" "Orchestrator" \
           "MLflow" "Kafka UI" "MinIO" "Prometheus" "Grafana" "Airflow" "Qdrant"; do
  url="${ENDPOINTS[$svc]}"
  result=$(curl -sf --max-time 3 -o /dev/null -w "%{http_code} %{time_total}" "${url}" 2>/dev/null || echo "000 0.000")
  http_code=$(echo "$result" | awk '{print $1}')
  latency=$(echo "$result" | awk '{printf "%.0fms", $2 * 1000}')

  if [[ "$http_code" =~ ^2 ]]; then
    status_icon="${GREEN}✅${NC}"
  elif [[ "$http_code" == "000" ]]; then
    status_icon="${RED}❌${NC}"
    latency="—"
  else
    status_icon="${YELLOW}⚠${NC} "
  fi

  printf "  %-20s %-40s %-10s %s\n" "$svc" "$url" "${http_code}" "${latency}"
  echo -ne "\033[1A\033[80C${status_icon}\033[0m\n"
done

echo ""

# ── Port mapping summary ──────────────────────────────────────────────────────
echo -e "${BOLD}Port Bindings:${NC}"
echo ""
printf "  %-14s %-8s %s\n" "Service" "Port" "Description"
printf "  %-14s %-8s %s\n" "-------" "----" "-----------"
printf "  %-14s %-8s %s\n" "gateway"      "8000"  "API Gateway (Nginx)"
printf "  %-14s %-8s %s\n" "vision-ai"    "8001"  "Vision AI service"
printf "  %-14s %-8s %s\n" "rag-engine"   "8002"  "RAG / vector search"
printf "  %-14s %-8s %s\n" "analytics"    "8004"  "Analytics service"
printf "  %-14s %-8s %s\n" "auth"         "8005"  "Auth / JWT service"
printf "  %-14s %-8s %s\n" "orchestrator" "8006"  "Multi-agent orchestrator"
printf "  %-14s %-8s %s\n" "kafka"        "9092"  "Kafka broker"
printf "  %-14s %-8s %s\n" "qdrant"       "6333"  "Qdrant vector DB"
printf "  %-14s %-8s %s\n" "redis"        "6379"  "Redis cache"
printf "  %-14s %-8s %s\n" "postgres"     "5432"  "PostgreSQL"
printf "  %-14s %-8s %s\n" "clickhouse"   "8123"  "ClickHouse analytics DB"
printf "  %-14s %-8s %s\n" "ollama"       "11434" "Ollama LLM server"
printf "  %-14s %-8s %s\n" "mlflow"       "5000"  "MLflow experiment tracking"
printf "  %-14s %-8s %s\n" "kafka-ui"     "8080"  "Kafka UI console"
printf "  %-14s %-8s %s\n" "minio"        "9001"  "MinIO console"
printf "  %-14s %-8s %s\n" "prometheus"   "9090"  "Prometheus metrics"
printf "  %-14s %-8s %s\n" "grafana"      "3001"  "Grafana dashboards"
printf "  %-14s %-8s %s\n" "airflow"      "8090"  "Airflow workflow UI"
echo ""
