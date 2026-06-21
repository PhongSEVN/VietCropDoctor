#!/usr/bin/env bash
# =============================================================================
# setup-server.sh — One-time setup for a fresh Ubuntu VPS / cloud instance
#
# Usage:
#   sudo ./scripts/setup-server.sh
#   sudo ./scripts/setup-server.sh --gpu        # Also install nvidia-container-toolkit
#   sudo ./scripts/setup-server.sh --no-swap    # Skip swap creation
#   sudo ./scripts/setup-server.sh --no-clone   # Skip git clone (useful if already cloned)
#
# Environment variables (override defaults):
#   SERVICES_REPO   Git URL for vietcropdoctor-services
#   INFRA_REPO      Git URL for vietcropdoctor-infra
#   ML_REPO         Git URL for vietcropdoctor-ml
#   PROJECT_DIR     Install directory (default: /opt/vietcropdoctor)
#   SWAP_SIZE       Swap size in GB (default: 4)
#
# Requires: Ubuntu 22.04+, run as root (sudo)
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; }
die()     { error "$*"; exit 1; }

# ── Root check ────────────────────────────────────────────────────────────────
if [[ $EUID -ne 0 ]]; then
  die "This script must be run as root (sudo $0)"
fi

# ── Config ────────────────────────────────────────────────────────────────────
PROJECT_DIR="${PROJECT_DIR:-/opt/vietcropdoctor}"
SERVICES_REPO="${SERVICES_REPO:-https://github.com/vietcropdoctor/vietcropdoctor-services.git}"
INFRA_REPO="${INFRA_REPO:-https://github.com/vietcropdoctor/vietcropdoctor-infra.git}"
ML_REPO="${ML_REPO:-https://github.com/vietcropdoctor/vietcropdoctor-ml.git}"
SWAP_SIZE="${SWAP_SIZE:-4}"

INSTALL_GPU=false
CREATE_SWAP=true
CLONE_REPOS=true

for arg in "$@"; do
  case $arg in
    --gpu)       INSTALL_GPU=true ;;
    --no-swap)   CREATE_SWAP=false ;;
    --no-clone)  CLONE_REPOS=false ;;
    --help|-h)
      echo "Usage: sudo $0 [--gpu] [--no-swap] [--no-clone]"
      exit 0
      ;;
    *) warn "Unknown argument: $arg" ;;
  esac
done

echo ""
echo -e "${BOLD}━━━ VietCropDoctor Server Setup ━━━${NC}"
echo -e "  Project dir : ${PROJECT_DIR}"
echo -e "  GPU support : ${INSTALL_GPU}"
echo -e "  Create swap : ${CREATE_SWAP} (${SWAP_SIZE}GB)"
echo -e "  Clone repos : ${CLONE_REPOS}"
echo ""

# ── Step 1: System packages ───────────────────────────────────────────────────
info "Step 1/9: Updating system packages…"
apt-get update -qq
apt-get install -y -qq \
  curl wget git ca-certificates gnupg lsb-release \
  ufw unzip jq htop vim net-tools
success "System packages installed"

# ── Step 2: Docker ────────────────────────────────────────────────────────────
info "Step 2/9: Installing Docker…"
if command -v docker >/dev/null 2>&1; then
  success "Docker already installed: $(docker --version)"
else
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \
    gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg

  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > \
    /etc/apt/sources.list.d/docker.list

  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin

  systemctl enable docker
  systemctl start docker
  success "Docker installed: $(docker --version)"
fi

# ── Step 3: kubectl ───────────────────────────────────────────────────────────
info "Step 3/9: Installing kubectl…"
if command -v kubectl >/dev/null 2>&1; then
  success "kubectl already installed: $(kubectl version --client --short 2>/dev/null || kubectl version --client)"
else
  KUBE_VER=$(curl -fsSL https://dl.k8s.io/release/stable.txt)
  curl -fsSL "https://dl.k8s.io/release/${KUBE_VER}/bin/linux/amd64/kubectl" -o /usr/local/bin/kubectl
  chmod +x /usr/local/bin/kubectl
  success "kubectl installed: $(kubectl version --client --short 2>/dev/null)"
fi

# kustomize
if ! command -v kustomize >/dev/null 2>&1; then
  info "  Installing kustomize…"
  curl -fsSL "https://raw.githubusercontent.com/kubernetes-sigs/kustomize/master/hack/install_kustomize.sh" | bash
  mv kustomize /usr/local/bin/
  success "kustomize installed: $(kustomize version)"
fi

# ── Step 4: NVIDIA container toolkit (optional) ───────────────────────────────
if [[ "$INSTALL_GPU" == "true" ]]; then
  info "Step 4/9: Installing nvidia-container-toolkit…"
  if dpkg -l | grep -q nvidia-container-toolkit; then
    success "nvidia-container-toolkit already installed"
  else
    distribution=$(. /etc/os-release; echo "${ID}${VERSION_ID}")
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
      gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -fsSL "https://nvidia.github.io/libnvidia-container/${distribution}/libnvidia-container.list" | \
      sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' > \
      /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update -qq
    apt-get install -y -qq nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
    success "nvidia-container-toolkit installed"
  fi
else
  info "Step 4/9: Skipping GPU setup (no --gpu flag)"
fi

# ── Step 5: Firewall ──────────────────────────────────────────────────────────
info "Step 5/9: Configuring firewall (ufw)…"
ufw --force reset >/dev/null 2>&1
ufw default deny incoming >/dev/null 2>&1
ufw default allow outgoing >/dev/null 2>&1
ufw allow 22/tcp comment 'SSH' >/dev/null 2>&1
ufw allow 80/tcp comment 'HTTP' >/dev/null 2>&1
ufw allow 443/tcp comment 'HTTPS' >/dev/null 2>&1
ufw --force enable >/dev/null 2>&1
success "Firewall configured: SSH(22), HTTP(80), HTTPS(443) open"

# ── Step 6: Swap ──────────────────────────────────────────────────────────────
if [[ "$CREATE_SWAP" == "true" ]]; then
  info "Step 6/9: Setting up ${SWAP_SIZE}GB swap…"
  SWAP_FILE="/swapfile"
  if swapon --show | grep -q "$SWAP_FILE" 2>/dev/null; then
    success "Swap already active"
  else
    fallocate -l "${SWAP_SIZE}G" "$SWAP_FILE"
    chmod 600 "$SWAP_FILE"
    mkswap "$SWAP_FILE" >/dev/null
    swapon "$SWAP_FILE"
    # Persist across reboots
    if ! grep -q "$SWAP_FILE" /etc/fstab; then
      echo "${SWAP_FILE} none swap sw 0 0" >> /etc/fstab
    fi
    # Reduce swappiness for server workloads
    echo "vm.swappiness=10" >> /etc/sysctl.conf
    sysctl -p >/dev/null 2>&1
    success "Swap created: $(free -h | grep Swap)"
  fi
else
  info "Step 6/9: Skipping swap (--no-swap)"
fi

# ── Step 7: Project directories ───────────────────────────────────────────────
info "Step 7/9: Creating project directory structure…"
mkdir -p "${PROJECT_DIR}"/{data/{qdrant,ollama,mlflow/artifacts,minio,airflow,training,models},logs}
chmod -R 755 "${PROJECT_DIR}"
success "Directories created: ${PROJECT_DIR}"

# ── Step 8: Clone repositories ───────────────────────────────────────────────
if [[ "$CLONE_REPOS" == "true" ]]; then
  info "Step 8/9: Cloning repositories…"
  cd "${PROJECT_DIR}"

  for repo_url in "$SERVICES_REPO" "$INFRA_REPO" "$ML_REPO"; do
    repo_name=$(basename "${repo_url}" .git)
    if [[ -d "${repo_name}/.git" ]]; then
      info "  ${repo_name} already cloned — pulling latest…"
      git -C "${repo_name}" pull --ff-only 2>/dev/null || warn "  Could not pull ${repo_name}"
    else
      info "  Cloning ${repo_url}…"
      git clone --depth=1 "${repo_url}" "${repo_name}" 2>/dev/null || \
        warn "  Could not clone ${repo_url} — set correct repo URL in env vars"
    fi
  done
  success "Repositories ready"
else
  info "Step 8/9: Skipping clone (--no-clone)"
fi

# ── Step 9: Generate .env with random secrets ────────────────────────────────
info "Step 9/9: Generating .env file…"
SERVICES_DIR="${PROJECT_DIR}/vietcropdoctor-services"
ENV_FILE="${SERVICES_DIR}/.env"

if [[ -f "$ENV_FILE" ]]; then
  warn ".env already exists — skipping generation (delete it to regenerate)"
else
  if [[ -f "${SERVICES_DIR}/example.env" ]]; then
    cp "${SERVICES_DIR}/example.env" "$ENV_FILE"
  fi

  # Generate random secrets
  JWT_SECRET=$(openssl rand -hex 32)
  POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '+=/' | head -c 20)
  MINIO_PASSWORD=$(openssl rand -base64 16 | tr -d '+=/' | head -c 16)

  cat > "$ENV_FILE" <<EOF
# Auto-generated by setup-server.sh — $(date -u +"%Y-%m-%dT%H:%M:%SZ")
# Review and update API keys before going live!

# Auth
JWT_SECRET=${JWT_SECRET}
POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
POSTGRES_DSN=postgresql://vcdauth:${POSTGRES_PASSWORD}@postgres:5432/vcd_auth
COOKIE_SECURE=true

# MinIO
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=${MINIO_PASSWORD}
MINIO_ENDPOINT=minio:9000
MINIO_BUCKET_UPLOADS=vcd-uploads
MINIO_STORE_UPLOADS=true

# Orchestrator
REASONING_MODEL=qwen2.5:7b
VISION_AI_URL=http://vision-ai:8001
RAG_ENGINE_URL=http://rag-engine:8002

# Qdrant
QDRANT_HOST=qdrant
QDRANT_PORT=6333

# TODO: Fill in these values before deploying
OPENAI_API_KEY=YOUR_OPENAI_KEY
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMS_API_KEY=your-sms-api-key
SMS_API_URL=https://api.twilio.com/2010-04-01/Accounts/ACXXX/Messages.json
ALERT_EMAIL_TO=admin@example.com
EOF

  chmod 600 "$ENV_FILE"
  success ".env generated with random secrets"
  warn "IMPORTANT: Update OPENAI_API_KEY, SMTP_*, SMS_* before deploying!"
fi

# ── Final summary ─────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}Server setup complete!${NC}"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo "  1. Review and complete ${ENV_FILE}"
echo "  2. cd ${SERVICES_DIR}"
echo "  3. ./scripts/local-start.sh   # or docker compose up -d"
echo "  4. Configure nginx reverse proxy for TLS (Let's Encrypt)"
echo ""
echo -e "${BOLD}Useful commands:${NC}"
echo "  docker compose ps          — service status"
echo "  docker compose logs -f     — follow all logs"
echo "  ufw status                 — firewall status"
echo "  free -h                    — memory + swap"
echo ""
