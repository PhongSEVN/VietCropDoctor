#!/usr/bin/env bash
# =============================================================================
# docker/stop.sh — Dừng VietCropDoctor local development stack
#
# Usage:
#   ./scripts/docker/stop.sh           # Graceful stop (keep volumes)
#   ./scripts/docker/stop.sh --clean   # Stop + remove volumes + prune images
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
CLEAN=false

for arg in "$@"; do
  case $arg in
    --clean)   CLEAN=true ;;
    --help|-h)
      echo "Usage: $0 [--clean]"
      echo "  --clean   Also remove volumes and prune dangling images"
      exit 0
      ;;
    *) warn "Unknown argument: $arg" ;;
  esac
done

echo ""
echo -e "${BOLD}━━━ VietCropDoctor — Stop ━━━${NC}"
echo ""

info "Stopping all services…"
if [[ "$CLEAN" == "true" ]]; then
  $COMPOSE down -v --remove-orphans
  success "Services stopped and volumes removed"

  info "Pruning dangling images…"
  docker image prune -f 2>/dev/null || true
  success "Dangling images pruned"
else
  $COMPOSE down --remove-orphans
  success "Services stopped (data volumes preserved)"
  info "Run with --clean to also remove volumes and prune images"
fi

echo ""
info "Docker disk usage after stop:"
docker system df 2>/dev/null || true

echo ""
success "VietCropDoctor stack stopped."
echo ""
