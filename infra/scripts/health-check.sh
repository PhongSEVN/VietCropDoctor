#!/usr/bin/env bash
# =============================================================================
# health-check.sh — Hit /health on all VietCropDoctor service endpoints
#
# Usage:
#   ./scripts/health-check.sh                    # One-shot check (human output)
#   ./scripts/health-check.sh --json             # Machine-readable JSON output
#   ./scripts/health-check.sh --loop             # Run every 30 seconds
#   ./scripts/health-check.sh --loop --interval=60  # Custom interval (seconds)
#   ./scripts/health-check.sh --base-url=https://api.example.com  # Remote target
#
# Exit codes:
#   0  All services healthy
#   1  One or more services unhealthy
#
# Requires: curl, jq (only for --json pretty-print)
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# ── Config ────────────────────────────────────────────────────────────────────
JSON_OUTPUT=false
LOOP=false
INTERVAL=30
BASE_URL=""

for arg in "$@"; do
  case $arg in
    --json)           JSON_OUTPUT=true ;;
    --loop)           LOOP=true ;;
    --interval=*)     INTERVAL="${arg#*=}" ;;
    --base-url=*)     BASE_URL="${arg#*=}" ;;
    --help|-h)
      echo "Usage: $0 [--json] [--loop] [--interval=N] [--base-url=URL]"
      echo ""
      echo "  --json            Output results as JSON (non-zero exit if any fail)"
      echo "  --loop            Run continuously every --interval seconds"
      echo "  --interval=N      Polling interval in seconds (default: 30)"
      echo "  --base-url=URL    Override base URL (default: http://localhost)"
      exit 0
      ;;
    *) warn "Unknown argument: $arg" ;;
  esac
done

# ── Service endpoints ─────────────────────────────────────────────────────────
declare -A SERVICES
SERVICES=(
  ["gateway"]="${BASE_URL:-http://localhost}:8000/health"
  ["vision-ai"]="${BASE_URL:-http://localhost}:8001/health"
  ["rag-engine"]="${BASE_URL:-http://localhost}:8002/health"
  ["analytics"]="${BASE_URL:-http://localhost}:8004/health"
  ["auth"]="${BASE_URL:-http://localhost}:8005/health"
  ["orchestrator"]="${BASE_URL:-http://localhost}:8006/health"
  ["prometheus"]="${BASE_URL:-http://localhost}:9090/-/healthy"
  ["grafana"]="${BASE_URL:-http://localhost}:3001/api/health"
  ["qdrant"]="${BASE_URL:-http://localhost}:6333/healthz"
)

# ── Check function ────────────────────────────────────────────────────────────
run_checks() {
  local timestamp
  timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
  local total=0 healthy=0 unhealthy=0

  if [[ "$JSON_OUTPUT" == "false" ]]; then
    echo ""
    echo -e "${BOLD}━━━ VietCropDoctor Health Check — ${timestamp} ━━━${NC}"
    echo ""
    printf "  %-16s %-45s %-8s %s\n" "Service" "URL" "HTTP" "Latency"
    printf "  %-16s %-45s %-8s %s\n" "-------" "---" "----" "-------"
  fi

  declare -A results=()

  for svc in gateway vision-ai rag-engine analytics auth orchestrator \
             prometheus grafana qdrant; do
    url="${SERVICES[$svc]}"
    total=$((total + 1))

    # curl with timing
    result=$(curl -sf --max-time 5 \
      -o /dev/null \
      -w "%{http_code} %{time_total}" \
      "${url}" 2>/dev/null || echo "000 0.000")

    http_code=$(echo "$result" | awk '{print $1}')
    time_total=$(echo "$result" | awk '{print $2}')
    latency_ms=$(echo "$time_total" | awk '{printf "%d", $1 * 1000}')

    if [[ "$http_code" =~ ^2 ]]; then
      status="healthy"
      healthy=$((healthy + 1))
    else
      status="unhealthy"
      unhealthy=$((unhealthy + 1))
    fi

    results["$svc"]="${status}|${http_code}|${latency_ms}"

    if [[ "$JSON_OUTPUT" == "false" ]]; then
      if [[ "$status" == "healthy" ]]; then
        icon="${GREEN}✅${NC}"
      elif [[ "$http_code" == "000" ]]; then
        icon="${RED}❌ OFFLINE${NC}"
      else
        icon="${YELLOW}⚠  HTTP ${http_code}${NC}"
      fi
      printf "  %-16s %-45s %-8s %sms\n" "$svc" "$url" "$http_code" "$latency_ms"
      # Overwrite the line with color
      echo -ne "\033[1A\033[$(( 16 + 45 + 8 + 5 + 3 ))C${icon}\n"
    fi
  done

  if [[ "$JSON_OUTPUT" == "true" ]]; then
    # Build JSON
    local json='{"timestamp":"'"${timestamp}"'","summary":{"total":'"${total}"',"healthy":'"${healthy}"',"unhealthy":'"${unhealthy}"'},"services":{'
    local first=true
    for svc in "${!results[@]}"; do
      IFS='|' read -r status http_code latency_ms <<< "${results[$svc]}"
      [[ "$first" == "false" ]] && json+=","
      json+='"'"${svc}"'":{"status":"'"${status}"'","http_code":'"${http_code}"',"latency_ms":'"${latency_ms}"',"url":"'"${SERVICES[$svc]}"'"}'
      first=false
    done
    json+="}}"

    if command -v jq >/dev/null 2>&1; then
      echo "$json" | jq .
    else
      echo "$json"
    fi
  else
    echo ""
    if [[ $unhealthy -eq 0 ]]; then
      success "All ${healthy}/${total} services healthy"
    else
      warn "${unhealthy}/${total} services unhealthy"
      echo ""
    fi
  fi

  # Return exit code
  [[ $unhealthy -eq 0 ]]
}

# ── Main ──────────────────────────────────────────────────────────────────────
if [[ "$LOOP" == "true" ]]; then
  if [[ "$JSON_OUTPUT" == "false" ]]; then
    info "Running health checks every ${INTERVAL}s. Press Ctrl+C to stop."
  fi
  OVERALL_EXIT=0
  while true; do
    run_checks || OVERALL_EXIT=1
    sleep "${INTERVAL}"
  done
  exit $OVERALL_EXIT
else
  run_checks
fi
