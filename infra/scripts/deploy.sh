#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Build, push, and deploy VietCropDoctor to Kubernetes
#
# Usage:
#   ./scripts/deploy.sh staging          # Deploy to staging environment
#   ./scripts/deploy.sh prod             # Deploy to production (requires approval)
#   ./scripts/deploy.sh staging --skip-build  # Deploy without rebuilding images
#   ./scripts/deploy.sh staging --dry-run     # Render manifests without applying
#
# Environment variables:
#   DOCKER_REGISTRY  Registry prefix (default: ghcr.io/vietcropdoctor)
#   KUBECONFIG       Path to kubeconfig (default: ~/.kube/config)
#   NAMESPACE        Override target namespace
#
# Requires: docker, kubectl, kustomize, git
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
REPO_ROOT="$(cd "${INFRA_ROOT}/.." && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

# ── Parse arguments ───────────────────────────────────────────────────────────
ENV="${1:-}"
SKIP_BUILD=false
DRY_RUN=false

if [[ -z "$ENV" ]]; then
  echo "Usage: $0 <staging|prod> [--skip-build] [--dry-run]"
  exit 1
fi

shift
for arg in "$@"; do
  case $arg in
    --skip-build) SKIP_BUILD=true ;;
    --dry-run)    DRY_RUN=true ;;
    --help|-h)
      echo "Usage: $0 <staging|prod> [--skip-build] [--dry-run]"
      exit 0
      ;;
    *) warn "Unknown argument: $arg" ;;
  esac
done

# ── Validate environment ──────────────────────────────────────────────────────
case "$ENV" in
  staging|prod) ;;
  *) die "Invalid environment '${ENV}'. Must be 'staging' or 'prod'." ;;
esac

DOCKER_REGISTRY="${DOCKER_REGISTRY:-ghcr.io/vietcropdoctor}"
NAMESPACE="${NAMESPACE:-vcd-${ENV}}"
OVERLAY_DIR="${INFRA_ROOT}/k8s/overlays/${ENV}"

if [[ ! -d "$OVERLAY_DIR" ]]; then
  die "Kustomize overlay not found: ${OVERLAY_DIR}"
fi

# ── Git info for image tags ───────────────────────────────────────────────────
GIT_SHA=$(git -C "${REPO_ROOT}" rev-parse --short HEAD 2>/dev/null || echo "unknown")
IMAGE_TAG="${ENV}-${GIT_SHA}"

echo ""
echo -e "${BOLD}━━━ VietCropDoctor Deploy ━━━${NC}"
echo -e "  Environment : ${BOLD}${ENV}${NC}"
echo -e "  Image tag   : ${IMAGE_TAG}"
echo -e "  Registry    : ${DOCKER_REGISTRY}"
echo -e "  Namespace   : ${NAMESPACE}"
echo -e "  Dry run     : ${DRY_RUN}"
echo ""

# ── Step 1: Prerequisites ─────────────────────────────────────────────────────
info "Step 1/7: Checking prerequisites…"

command -v docker    >/dev/null 2>&1 || die "docker not found"
command -v kubectl   >/dev/null 2>&1 || die "kubectl not found"
command -v kustomize >/dev/null 2>&1 || die "kustomize not found. Install: https://kubectl.docs.kubernetes.io/installation/kustomize/"

# kubectl context
CURRENT_CTX=$(kubectl config current-context 2>/dev/null || echo "none")
success "kubectl context: ${CURRENT_CTX}"

# Namespace check
if kubectl get namespace "${NAMESPACE}" >/dev/null 2>&1; then
  success "Namespace '${NAMESPACE}' exists"
else
  if [[ "$DRY_RUN" == "true" ]]; then
    warn "Namespace '${NAMESPACE}' does not exist (dry-run — skipping creation)"
  else
    info "Creating namespace '${NAMESPACE}'…"
    kubectl create namespace "${NAMESPACE}"
    success "Namespace created"
  fi
fi

# Registry connectivity
if [[ "$SKIP_BUILD" == "false" ]]; then
  docker info >/dev/null 2>&1 || die "Docker daemon is not running"
  success "Docker daemon running"
fi

# ── Step 2: Build images ──────────────────────────────────────────────────────
SERVICES=(vision-ai rag-engine analytics auth orchestrator gateway)

if [[ "$SKIP_BUILD" == "false" ]]; then
  info "Step 2/7: Building Docker images…"
  SERVICES_DIR="${REPO_ROOT}/vietcropdoctor-services/services"

  for svc in "${SERVICES[@]}"; do
    local_image="${DOCKER_REGISTRY}/${svc}:${IMAGE_TAG}"
    latest_image="${DOCKER_REGISTRY}/${svc}:${ENV}-latest"
    svc_dir="${SERVICES_DIR}/${svc}"

    if [[ ! -d "$svc_dir" ]]; then
      warn "Service directory not found: ${svc_dir} — skipping"
      continue
    fi

    info "  Building ${svc}…"
    docker build \
      --build-context services="${SERVICES_DIR}" \
      -t "${local_image}" \
      -t "${latest_image}" \
      -f "${svc_dir}/Dockerfile" \
      "${SERVICES_DIR}" 2>&1 | tail -5

    success "  ${svc} built: ${local_image}"
  done
else
  info "Step 2/7: Skipping build (--skip-build)"
fi

# ── Step 3: Push images ───────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" == "false" && "$DRY_RUN" == "false" ]]; then
  info "Step 3/7: Pushing images to registry…"
  for svc in "${SERVICES[@]}"; do
    local_image="${DOCKER_REGISTRY}/${svc}:${IMAGE_TAG}"
    latest_image="${DOCKER_REGISTRY}/${svc}:${ENV}-latest"

    docker push "${local_image}" 2>&1 | tail -3
    docker push "${latest_image}" 2>&1 | tail -3
    success "  Pushed: ${local_image}"
  done
else
  info "Step 3/7: Skipping push (dry-run or skip-build)"
fi

# ── Step 4: Apply Kubernetes manifests ───────────────────────────────────────
info "Step 4/7: Applying Kubernetes manifests (kustomize overlay: ${ENV})…"

KUSTOMIZE_OUTPUT=$(kustomize build "${OVERLAY_DIR}" 2>/dev/null)

if [[ "$DRY_RUN" == "true" ]]; then
  info "  Dry-run — printing rendered manifests:"
  echo "---"
  echo "${KUSTOMIZE_OUTPUT}" | head -100
  echo "  … (truncated)"
  success "Dry-run complete. No changes applied."
  exit 0
fi

echo "${KUSTOMIZE_OUTPUT}" | kubectl apply -n "${NAMESPACE}" -f -
success "Manifests applied"

# ── Step 5: Wait for rollout ──────────────────────────────────────────────────
info "Step 5/7: Waiting for deployments to roll out…"

DEPLOYMENTS=$(kubectl get deployments -n "${NAMESPACE}" -o jsonpath='{.items[*].metadata.name}' 2>/dev/null)
for deploy in ${DEPLOYMENTS}; do
  echo -ne "  Rolling out ${deploy}…"
  if kubectl rollout status deployment/"${deploy}" -n "${NAMESPACE}" --timeout=300s >/dev/null 2>&1; then
    echo -e "\r  ${GREEN}✓${NC} ${deploy} ready                         "
  else
    echo -e "\r  ${RED}✗${NC} ${deploy} rollout failed               "
    error "Deployment '${deploy}' failed. Check: kubectl logs -n ${NAMESPACE} -l app=${deploy}"
  fi
done

# ── Step 6: Smoke tests ───────────────────────────────────────────────────────
info "Step 6/7: Running smoke tests via port-forward…"

declare -A SVC_PORTS=(
  ["gateway"]="8000"
  ["vision-ai"]="8001"
  ["rag-engine"]="8002"
  ["auth"]="8005"
)

SMOKE_PASS=0
SMOKE_FAIL=0

for svc in "${!SVC_PORTS[@]}"; do
  port="${SVC_PORTS[$svc]}"
  local_port=$((port + 10000))  # avoid conflicts

  # Check if K8s service exists
  if ! kubectl get service "${svc}" -n "${NAMESPACE}" >/dev/null 2>&1; then
    warn "  Service '${svc}' not found in namespace — skipping"
    continue
  fi

  # Port-forward in background
  kubectl port-forward "service/${svc}" "${local_port}:${port}" -n "${NAMESPACE}" >/dev/null 2>&1 &
  PF_PID=$!
  sleep 2

  http_code=$(curl -sf --max-time 5 -o /dev/null -w "%{http_code}" \
    "http://localhost:${local_port}/health" 2>/dev/null || echo "000")

  kill $PF_PID 2>/dev/null || true

  if [[ "$http_code" =~ ^2 ]]; then
    echo -e "  ${GREEN}✓${NC} ${svc} /health → HTTP ${http_code}"
    SMOKE_PASS=$((SMOKE_PASS + 1))
  else
    echo -e "  ${RED}✗${NC} ${svc} /health → HTTP ${http_code}"
    SMOKE_FAIL=$((SMOKE_FAIL + 1))
  fi
done

if [[ $SMOKE_FAIL -gt 0 ]]; then
  warn "${SMOKE_FAIL} smoke test(s) failed — deployment may be unhealthy"
else
  success "All smoke tests passed (${SMOKE_PASS}/${SMOKE_PASS})"
fi

# ── Step 7: Summary ───────────────────────────────────────────────────────────
info "Step 7/7: Deployment summary"
echo ""
echo -e "${BOLD}Pod Status:${NC}"
kubectl get pods -n "${NAMESPACE}" 2>/dev/null
echo ""
echo -e "${BOLD}Services:${NC}"
kubectl get services -n "${NAMESPACE}" 2>/dev/null
echo ""

echo -e "${GREEN}${BOLD}Deployment to ${ENV} complete!${NC}"
echo -e "  Image tag: ${IMAGE_TAG}"
echo -e "  Namespace: ${NAMESPACE}"
echo ""
