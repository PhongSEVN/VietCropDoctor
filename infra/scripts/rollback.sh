#!/usr/bin/env bash
# =============================================================================
# rollback.sh — Roll back VietCropDoctor Kubernetes deployments
#
# Usage:
#   ./scripts/rollback.sh staging          # Roll back all deployments in staging
#   ./scripts/rollback.sh prod             # Roll back all deployments in prod
#   ./scripts/rollback.sh staging vision-ai  # Roll back a single service
#
# Requires: kubectl
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

ENV="${1:-}"
TARGET_SVC="${2:-}"  # optional: roll back only this service

if [[ -z "$ENV" ]]; then
  echo "Usage: $0 <staging|prod> [service-name]"
  exit 1
fi

case "$ENV" in
  staging|prod) ;;
  *) die "Invalid environment '${ENV}'. Must be 'staging' or 'prod'." ;;
esac

NAMESPACE="${NAMESPACE:-vcd-${ENV}}"

echo ""
echo -e "${BOLD}━━━ VietCropDoctor Rollback ━━━${NC}"
echo -e "  Environment : ${BOLD}${ENV}${NC}"
echo -e "  Namespace   : ${NAMESPACE}"
[[ -n "$TARGET_SVC" ]] && echo -e "  Service     : ${TARGET_SVC}" || echo -e "  Service     : ALL"
echo ""

# ── Prerequisites ─────────────────────────────────────────────────────────────
command -v kubectl >/dev/null 2>&1 || die "kubectl not found"

CURRENT_CTX=$(kubectl config current-context 2>/dev/null || echo "none")
success "kubectl context: ${CURRENT_CTX}"

kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1 || \
  die "Namespace '${NAMESPACE}' does not exist"

# ── Show current state before rollback ───────────────────────────────────────
info "Current deployment state:"
kubectl get deployments -n "${NAMESPACE}" \
  -o custom-columns='NAME:.metadata.name,DESIRED:.spec.replicas,READY:.status.readyReplicas,IMAGE:.spec.template.spec.containers[0].image' \
  2>/dev/null
echo ""

# ── Confirm for production ────────────────────────────────────────────────────
if [[ "$ENV" == "prod" ]]; then
  warn "You are rolling back PRODUCTION."
  read -r -p "Type 'yes' to confirm: " CONFIRM
  if [[ "$CONFIRM" != "yes" ]]; then
    info "Rollback cancelled."
    exit 0
  fi
fi

# ── Perform rollback ──────────────────────────────────────────────────────────
if [[ -n "$TARGET_SVC" ]]; then
  DEPLOYMENTS=("$TARGET_SVC")
else
  mapfile -t DEPLOYMENTS < <(kubectl get deployments -n "${NAMESPACE}" -o jsonpath='{range .items[*]}{.metadata.name}{"\n"}{end}' 2>/dev/null)
fi

FAIL=0
for deploy in "${DEPLOYMENTS[@]}"; do
  info "Rolling back deployment/${deploy}…"

  # Show rollout history
  kubectl rollout history "deployment/${deploy}" -n "${NAMESPACE}" 2>/dev/null | tail -3

  kubectl rollout undo "deployment/${deploy}" -n "${NAMESPACE}" 2>/dev/null || {
    warn "  Could not undo ${deploy} (may have no previous revision)"
    FAIL=$((FAIL + 1))
    continue
  }

  # Wait for rollback to complete
  echo -ne "  Waiting for ${deploy} to stabilize…"
  if kubectl rollout status "deployment/${deploy}" -n "${NAMESPACE}" --timeout=180s >/dev/null 2>&1; then
    echo -e "\r  ${GREEN}✓${NC} ${deploy} rolled back successfully           "
  else
    echo -e "\r  ${RED}✗${NC} ${deploy} rollback timed out                  "
    FAIL=$((FAIL + 1))
  fi
done

# ── Verify health after rollback ──────────────────────────────────────────────
echo ""
info "Verifying pod health after rollback…"
kubectl get pods -n "${NAMESPACE}" 2>/dev/null
echo ""

UNHEALTHY=$(kubectl get pods -n "${NAMESPACE}" \
  --field-selector='status.phase!=Running' \
  -o jsonpath='{.items[*].metadata.name}' 2>/dev/null || true)

if [[ -n "$UNHEALTHY" ]]; then
  warn "Non-running pods after rollback: ${UNHEALTHY}"
  warn "Check with: kubectl describe pod <name> -n ${NAMESPACE}"
else
  success "All pods are running"
fi

echo ""
if [[ $FAIL -gt 0 ]]; then
  warn "Rollback completed with ${FAIL} failure(s)"
  exit 1
else
  success "Rollback to ${ENV} complete!"
fi
echo ""
