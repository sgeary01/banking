#!/usr/bin/env bash
# bootstrap-k3d.sh — full bring-up of the banking O11y demo on k3d
#
# Usage:
#   ./scripts/bootstrap-k3d.sh            # create cluster + build + deploy
#   ./scripts/bootstrap-k3d.sh --no-build # skip image builds (reuse existing)
#   ./scripts/bootstrap-k3d.sh --down     # tear everything down
set -euo pipefail

CLUSTER_NAME="banking"
REGISTRY="banking"
TAG="latest"

SERVICES=(
  api-gateway auth-service customer-service account-service
  transaction-service ledger-service fraud-service
  notification-service reporting-service chaos-service
)

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${BLUE}==>${RESET} ${BOLD}$*${RESET}"; }
success() { echo -e "${GREEN}✓${RESET} $*"; }
warn()    { echo -e "${YELLOW}⚠${RESET}  $*"; }
die()     { echo -e "${RED}✗${RESET} $*" >&2; exit 1; }

# ── Helpers ────────────────────────────────────────────────────────────────────
check_deps() {
  local missing=()
  for cmd in docker k3d helm kubectl; do
    command -v "$cmd" &>/dev/null || missing+=("$cmd")
  done
  if [[ ${#missing[@]} -gt 0 ]]; then
    die "Missing required tools: ${missing[*]}\n  Install k3d:   brew install k3d\n  Install helm:  brew install helm"
  fi
  success "All prerequisites found"
}

cluster_exists() {
  k3d cluster list 2>/dev/null | grep -q "^${CLUSTER_NAME} "
}

# ── Tear-down ──────────────────────────────────────────────────────────────────
if [[ "${1:-}" == "--down" ]]; then
  info "Tearing down cluster '${CLUSTER_NAME}'"
  if cluster_exists; then
    k3d cluster delete "$CLUSTER_NAME"
    success "Cluster deleted"
  else
    warn "Cluster '${CLUSTER_NAME}' not found — nothing to do"
  fi
  exit 0
fi

SKIP_BUILD=false
[[ "${1:-}" == "--no-build" ]] && SKIP_BUILD=true

# ── Resolve repo root ──────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$REPO_ROOT"

# ── Pre-flight ─────────────────────────────────────────────────────────────────
info "Checking prerequisites"
check_deps

# ── Cluster ────────────────────────────────────────────────────────────────────
if cluster_exists; then
  warn "Cluster '${CLUSTER_NAME}' already exists — skipping creation"
else
  info "Creating k3d cluster '${CLUSTER_NAME}'"
  k3d cluster create "$CLUSTER_NAME" \
    --port "30000:30000@server:0" \
    --port "30080:30080@server:0" \
    --port "30030:30030@server:0" \
    --k3s-arg "--disable=traefik@server:0" \
    --wait
  success "Cluster created"
fi

# Ensure kubectl context points at this cluster
kubectl config use-context "k3d-${CLUSTER_NAME}" &>/dev/null
success "kubectl context: k3d-${CLUSTER_NAME}"

# ── Build images ───────────────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" == true ]]; then
  warn "Skipping image builds (--no-build)"
else
  info "Building base image"
  docker build -t "${REGISTRY}/base:${TAG}" ./base

  info "Building service images"
  for svc in "${SERVICES[@]}"; do
    echo "  building ${svc}..."
    docker build \
      --build-arg BASE_IMAGE="${REGISTRY}/base:${TAG}" \
      -f "./services/${svc}/Dockerfile" \
      -t "${REGISTRY}/${svc}:${TAG}" \
      . \
      --quiet
  done

  info "Building frontend"
  docker build -t "${REGISTRY}/frontend:${TAG}" ./frontend --quiet
  success "All images built"
fi

# ── Import images into k3d ─────────────────────────────────────────────────────
info "Importing images into k3d (this takes a minute)"
IMAGES=("${REGISTRY}/base:${TAG}")
for svc in "${SERVICES[@]}"; do
  IMAGES+=("${REGISTRY}/${svc}:${TAG}")
done
IMAGES+=("${REGISTRY}/frontend:${TAG}")

k3d image import "${IMAGES[@]}" -c "$CLUSTER_NAME"
success "Images imported"

# ── Deploy banking app ─────────────────────────────────────────────────────────
info "Deploying banking app (Helm)"
helm upgrade --install banking ./helm/banking \
  --namespace banking --create-namespace \
  --values ./helm/banking/values.yaml \
  --wait --timeout 5m

success "Banking app deployed"

# ── Wait for pods ──────────────────────────────────────────────────────────────
info "Waiting for banking pods to be ready"
kubectl wait --for=condition=ready pod \
  --all -n banking --timeout=120s
success "All banking pods ready"

# ── Deploy monitoring ──────────────────────────────────────────────────────────
info "Deploying monitoring stack (Helm)"
helm upgrade --install monitoring ./helm/monitoring \
  --namespace monitoring --create-namespace \
  --values ./helm/monitoring/values.yaml \
  --wait --timeout 5m

success "Monitoring stack deployed"

info "Waiting for monitoring pods to be ready"
kubectl wait --for=condition=ready pod \
  --all -n monitoring --timeout=120s
success "All monitoring pods ready"

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════╗${RESET}"
echo -e "${GREEN}${BOLD}║     Banking O11y Demo — Ready!           ║${RESET}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════╝${RESET}"
echo ""
echo -e "  ${BOLD}Frontend${RESET}   →  http://localhost:30080"
echo -e "  ${BOLD}API Gateway${RESET} →  http://localhost:30000/docs"
echo -e "  ${BOLD}Grafana${RESET}    →  http://localhost:30030  (admin / admin)"
echo ""
echo -e "  Login with: alice@example.com / password123"
echo ""
