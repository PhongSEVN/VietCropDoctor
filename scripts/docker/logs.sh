#!/usr/bin/env bash
# =============================================================================
# docker/logs.sh — Xem logs cho VietCropDoctor services
#
# Usage:
#   ./scripts/docker/logs.sh                    # Aggregate logs from all app services (follow)
#   ./scripts/docker/logs.sh vision-ai          # Logs for a specific service (follow)
#   ./scripts/docker/logs.sh vision-ai --no-follow
#   ./scripts/docker/logs.sh --tail=100         # Show last N lines (default 50)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

YELLOW='\033[1;33m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }

FOLLOW=true
TAIL=50
SERVICE=""

for arg in "$@"; do
  case $arg in
    --no-follow)        FOLLOW=false ;;
    --tail=*)           TAIL="${arg#*=}" ;;
    --help|-h)
      echo "Usage: $0 [service-name] [--no-follow] [--tail=N]"
      echo ""
      echo "  service-name   vision-ai, rag-engine, analytics, auth,"
      echo "                 orchestrator, gateway, kafka, qdrant, redis, ..."
      echo "  --no-follow    Print logs and exit (don't stream)"
      echo "  --tail=N       Show last N lines (default: 50)"
      exit 0
      ;;
    -*)  warn "Unknown flag: $arg" ;;
    *)
      if [[ -z "$SERVICE" ]]; then
        SERVICE="$arg"
      else
        warn "Extra argument ignored: $arg"
      fi
      ;;
  esac
done

APP_SERVICES="vision-ai rag-engine analytics auth orchestrator gateway"

FOLLOW_FLAG=""
[[ "$FOLLOW" == "true" ]] && FOLLOW_FLAG="-f"

if [[ -n "$SERVICE" ]]; then
  echo -e "${CYAN}[INFO]${NC}  Showing logs for: ${BOLD}${SERVICE}${NC}"
  [[ "$FOLLOW" == "true" ]] && echo -e "${CYAN}[INFO]${NC}  Press Ctrl+C to stop"
  echo ""
  docker compose logs ${FOLLOW_FLAG} --tail="${TAIL}" "${SERVICE}"
else
  echo -e "${CYAN}[INFO]${NC}  Showing aggregated logs from all app services"
  [[ "$FOLLOW" == "true" ]] && echo -e "${CYAN}[INFO]${NC}  Press Ctrl+C to stop"
  echo -e "${CYAN}[INFO]${NC}  Services: ${APP_SERVICES}"
  echo ""
  # shellcheck disable=SC2086
  docker compose logs ${FOLLOW_FLAG} --tail="${TAIL}" ${APP_SERVICES}
fi
