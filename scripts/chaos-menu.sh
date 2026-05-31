#!/usr/bin/env bash
# chaos-menu.sh — Interactive chaos menu for the banking demo.
#
# Combines app-level chaos (via the chaos-service API) and
# infrastructure-level chaos (kubectl patches) into one place.

set -euo pipefail

GATEWAY="http://localhost:30000"
NAMESPACE="banking"

# ── Colours ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'

# ── Helpers ────────────────────────────────────────────────────────────────────

header() {
  clear
  echo -e "${BOLD}${CYAN}"
  echo "  ╔══════════════════════════════════════════════════════╗"
  echo "  ║           Banking Demo — Chaos Control               ║"
  echo "  ╚══════════════════════════════════════════════════════╝"
  echo -e "${RESET}"
}

section() { echo -e "\n${BOLD}${YELLOW}  $1${RESET}"; }

active_chaos() {
  local app_chaos infra_chaos=()

  app_chaos=$(curl -s "$GATEWAY/chaos/status" 2>/dev/null | python3 -c "
import json, sys
try:
    d = json.load(sys.stdin)
    active = [s for s,v in d.items() if v.get('active')]
    print(', '.join(active) if active else '')
except: print('')
" 2>/dev/null || echo "")

  kubectl get networkpolicy infra-chaos-block-fraud -n "$NAMESPACE" &>/dev/null \
    && infra_chaos+=("network-policy")

  local mem_limit
  mem_limit=$(kubectl get deployment transaction-service -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].resources.limits.memory}' 2>/dev/null || echo "")
  [[ "$mem_limit" == "90Mi" ]] && infra_chaos+=("oom")

  local cpu_limit
  cpu_limit=$(kubectl get deployment account-service -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].resources.limits.cpu}' 2>/dev/null || echo "")
  [[ "$cpu_limit" == "10m" ]] && infra_chaos+=("cpu-starvation")

  local jwt_secret
  jwt_secret=$(kubectl get deployment api-gateway -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="JWT_SECRET")].value}' 2>/dev/null || echo "")
  [[ "$jwt_secret" == "wrong-secret-rotation-failed" ]] && infra_chaos+=("jwt-rotation")

  local image
  image=$(kubectl get deployment reporting-service -n "$NAMESPACE" \
    -o jsonpath='{.spec.template.spec.containers[0].image}' 2>/dev/null || echo "")
  [[ "$image" == *"broken"* ]] && infra_chaos+=("bad-deployment")

  local all=()
  [[ -n "$app_chaos" ]] && all+=("$app_chaos")
  all+=("${infra_chaos[@]}")

  if [[ ${#all[@]} -gt 0 ]]; then
    echo -e "  ${RED}⚡ Active chaos:${RESET} ${all[*]}"
  else
    echo -e "  ${GREEN}✓ No active chaos${RESET}"
  fi
}

api_trigger() {
  local scenario=$1
  curl -s -X POST "$GATEWAY/chaos/scenarios/${scenario}/trigger" -o /dev/null
}

api_clear() {
  curl -s -X POST "$GATEWAY/chaos/scenarios/clear" -o /dev/null
}

wait_rollout() {
  echo -e "  ${DIM}Waiting for rollout...${RESET}"
  kubectl rollout status deployment/"$1" -n "$NAMESPACE" --timeout=90s 2>&1 \
    | grep -v "Waiting" || true
}

press_enter() {
  echo -e "\n  ${DIM}Press Enter to return to menu...${RESET}"
  read -r
}

confirm() {
  echo -e "\n  ${YELLOW}$1${RESET} [y/N] "
  read -r -n1 ans
  echo
  [[ "$ans" =~ ^[Yy]$ ]]
}

# ── App-level chaos actions ────────────────────────────────────────────────────

do_payment_outage() {
  echo -e "\n  ${RED}Triggering claims processing outage...${RESET}"
  api_trigger claims_processing_outage
  echo -e "  ${GREEN}✓ Done${RESET}"
  echo -e "\n  ${DIM}transaction-service (claims backend) → ~50% errors"
  echo -e "  Alerts: ClaimsProcessingErrorRate (1m), SuspiciousClaimsSpike (side effect)"
  echo -e "  Dashboard: Claims & Premiums${RESET}"
  press_enter
}

do_high_latency() {
  echo -e "\n  ${RED}Triggering policy lookup latency...${RESET}"
  api_trigger policy_lookup_latency
  echo -e "  ${GREEN}✓ Done${RESET}"
  echo -e "\n  ${DIM}account-service (policy lookup) → 3s delay on all requests"
  echo -e "  Alerts: HighLatency (2m)"
  echo -e "  Dashboard: Service Health, Coverage Overview${RESET}"
  press_enter
}

do_fraud_spike() {
  echo -e "\n  ${RED}Triggering suspicious claims spike...${RESET}"
  api_trigger suspicious_claims_spike
  echo -e "  ${GREEN}✓ Done${RESET}"
  echo -e "\n  ${DIM}Burst of high-value claim submissions → investigation service overload"
  echo -e "  Alerts: SuspiciousClaimsSpike (1m)"
  echo -e "  Dashboard: Claim Investigations${RESET}"
  press_enter
}

do_cascade() {
  echo -e "\n  ${RED}Triggering cascade failure...${RESET}"
  api_trigger cascade_failure
  echo -e "  ${GREEN}✓ Done${RESET}"
  echo -e "\n  ${DIM}Claims + policy lookup services both degraded"
  echo -e "  Alerts: ClaimsProcessingErrorRate + HighLatency simultaneously"
  echo -e "  Dashboard: Coverage Overview, Service Health${RESET}"
  press_enter
}

do_notification_flood() {
  echo -e "\n  ${RED}Triggering notification flood...${RESET}"
  api_trigger notification_flood
  echo -e "  ${GREEN}✓ Done${RESET}"
  echo -e "\n  ${DIM}Many claim submissions → notification-service latency"
  echo -e "  Alerts: HighLatency on notification-service (2m)"
  echo -e "  Dashboard: Service Health${RESET}"
  press_enter
}

# ── Infra chaos actions ────────────────────────────────────────────────────────

do_oom() {
  echo -e "\n  ${RED}Triggering OOM scenario...${RESET}"
  kubectl patch deployment transaction-service -n "$NAMESPACE" --type=json -p='[
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"64Mi"},
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"90Mi"}
  ]' 2>&1 | grep -v "^$"
  wait_rollout transaction-service
  echo -e "\n  ${DIM}transaction-service memory limit → 90Mi (was 192Mi, resting usage ~84MB)"
  echo -e "  Any transaction load will trigger an OOM kill"
  echo -e "  Alerts: PodCrashLooping (after restarts)"
  echo -e "  Dashboard: K8s & Pod Health → container memory %, restart rate${RESET}"
  press_enter
}

do_jwt() {
  echo -e "\n  ${RED}Triggering JWT rotation failure...${RESET}"
  kubectl set env deployment/api-gateway -n "$NAMESPACE" \
    JWT_SECRET=wrong-secret-rotation-failed 2>&1 | grep -v "^$"
  wait_rollout api-gateway
  echo -e "\n  ${DIM}api-gateway → wrong JWT secret, all tokens rejected with 401"
  echo -e "  auth-service looks healthy, no 5xx errors anywhere"
  echo -e "  Alerts: HighClientErrorRate (2m) — only 4xx signal fires"
  echo -e "  Dashboard: Service Health → 4xx rate${RESET}"
  press_enter
}

do_netpolicy() {
  echo -e "\n  ${RED}Triggering network blackout on fraud-service...${RESET}"
  kubectl apply -f - <<EOF 2>&1 | grep -v "^$"
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: infra-chaos-block-fraud
  namespace: $NAMESPACE
  labels:
    infra-chaos: "true"
spec:
  podSelector:
    matchLabels:
      app: fraud-service
  policyTypes:
    - Ingress
  ingress: []
EOF
  echo -e "\n  ${DIM}fraud-service ingress blocked — unreachable from transaction-service"
  echo -e "  fraud-service /health still returns 200"
  echo -e "  Alerts: CriticalErrorRate on transaction-service"
  echo -e "  Dashboard: Traces & Service Map → broken edge in service graph${RESET}"
  press_enter
}

do_cpu() {
  echo -e "\n  ${RED}Triggering CPU starvation on account-service...${RESET}"
  kubectl patch deployment account-service -n "$NAMESPACE" --type=json -p='[
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/cpu","value":"10m"}
  ]' 2>&1 | grep -v "^$"
  wait_rollout account-service
  echo -e "\n  ${DIM}account-service CPU limit → 10m (was 250m)"
  echo -e "  No errors — pure latency degradation"
  echo -e "  Alerts: HighLatency (2m)"
  echo -e "  Dashboard: K8s & Pod Health → CPU throttle rate spike${RESET}"
  press_enter
}

do_bad_deploy() {
  echo -e "\n  ${RED}Triggering bad deployment on reporting-service...${RESET}"
  kubectl patch deployment reporting-service -n "$NAMESPACE" --type=json -p='[
    {"op":"replace","path":"/spec/template/spec/containers/0/image","value":"banking/reporting-service:broken-v2"}
  ]' 2>&1 | grep -v "^$"
  echo -e "\n  ${DIM}reporting-service rolling out broken image tag"
  echo -e "  New pods → ImagePullBackOff, old pod stays running (partial degradation)"
  echo -e "  Alerts: DeploymentReplicasMismatch (2m)"
  echo -e "  Dashboard: K8s & Pod Health → replicas mismatch${RESET}"
  press_enter
}

# ── Clear actions ──────────────────────────────────────────────────────────────

do_clear_app() {
  echo -e "\n  ${GREEN}Clearing app-level chaos...${RESET}"
  api_clear
  echo -e "  ${GREEN}✓ App chaos cleared${RESET}"
  press_enter
}

do_clear_all() {
  echo -e "\n  ${GREEN}Clearing all chaos (app + infra)...${RESET}"

  api_clear
  echo -e "  ${GREEN}✓ App chaos cleared${RESET}"

  kubectl patch deployment transaction-service -n "$NAMESPACE" --type=json -p='[
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"96Mi"},
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"192Mi"}
  ]' &>/dev/null && echo -e "  ${GREEN}✓ OOM restored${RESET}" || true

  kubectl set env deployment/api-gateway -n "$NAMESPACE" \
    JWT_SECRET=dev-secret-change-in-prod &>/dev/null \
    && echo -e "  ${GREEN}✓ JWT secret restored${RESET}" || true

  kubectl delete networkpolicy infra-chaos-block-fraud -n "$NAMESPACE" \
    --ignore-not-found &>/dev/null \
    && echo -e "  ${GREEN}✓ Network policy removed${RESET}" || true

  kubectl patch deployment account-service -n "$NAMESPACE" --type=json -p='[
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/cpu","value":"250m"}
  ]' &>/dev/null && echo -e "  ${GREEN}✓ CPU limit restored${RESET}" || true

  kubectl patch deployment reporting-service -n "$NAMESPACE" --type=json -p='[
    {"op":"replace","path":"/spec/template/spec/containers/0/image","value":"banking/reporting-service:latest"}
  ]' &>/dev/null && echo -e "  ${GREEN}✓ Deployment image restored${RESET}" || true

  echo -e "\n  ${DIM}Waiting for any pending rollouts...${RESET}"
  for svc in transaction-service api-gateway account-service reporting-service; do
    kubectl rollout status deployment/"$svc" -n "$NAMESPACE" --timeout=60s &>/dev/null || true
  done

  echo -e "\n  ${GREEN}✓ All chaos cleared${RESET}"
  press_enter
}

# ── Menus ──────────────────────────────────────────────────────────────────────

menu_app_chaos() {
  while true; do
    header
    section "App-Level Chaos  (via chaos-service API)"
    echo -e "  ${DIM}Injected into running services — clears automatically or via Clear All${RESET}\n"
    echo "  1) Payment outage       — transaction-service 50% errors"
    echo "  2) High latency         — account-service 3s delays"
    echo "  3) Fraud spike          — burst of high-value transactions"
    echo "  4) Cascade failure      — transaction + account both degraded"
    echo "  5) Notification flood   — overload notification-service"
    echo "  6) Clear app chaos"
    echo ""
    echo "  0) Back"
    echo ""
    active_chaos
    echo -e "\n  ${BOLD}Choice:${RESET} "
    read -r -n1 choice
    case "$choice" in
      1) do_payment_outage ;;
      2) do_high_latency ;;
      3) do_fraud_spike ;;
      4) do_cascade ;;
      5) do_notification_flood ;;
      6) do_clear_app ;;
      0) return ;;
    esac
  done
}

menu_infra_chaos() {
  while true; do
    header
    section "Infrastructure Chaos  (kubectl patches — not tied to chaos service)"
    echo -e "  ${DIM}Look like real operational incidents. Cleared via Clear All or individually.${RESET}\n"
    echo "  1) OOM kill             — transaction-service memory limit → 90Mi"
    echo "  2) JWT rotation failure — api-gateway rejects all auth tokens (401s)"
    echo "  3) Network blackout     — fraud-service ingress blocked"
    echo "  4) CPU starvation       — account-service throttled to 10m CPU"
    echo "  5) Bad deployment       — reporting-service broken image rollout"
    echo ""
    echo "  0) Back"
    echo ""
    active_chaos
    echo -e "\n  ${BOLD}Choice:${RESET} "
    read -r -n1 choice
    case "$choice" in
      1) do_oom ;;
      2) do_jwt ;;
      3) do_netpolicy ;;
      4) do_cpu ;;
      5) do_bad_deploy ;;
      0) return ;;
    esac
  done
}

main_menu() {
  while true; do
    header
    section "Main Menu"
    echo ""
    echo "  1) App-level chaos      (payment outage, latency, fraud spike...)"
    echo "  2) Infrastructure chaos (OOM, JWT, network policy, CPU, bad deploy)"
    echo "  3) Clear ALL chaos"
    echo ""
    echo "  0) Exit"
    echo ""
    active_chaos
    echo -e "\n  ${BOLD}Choice:${RESET} "
    read -r -n1 choice
    echo
    case "$choice" in
      1) menu_app_chaos ;;
      2) menu_infra_chaos ;;
      3) do_clear_all ;;
      0) echo -e "\n  ${DIM}Bye.${RESET}\n"; exit 0 ;;
    esac
  done
}

main_menu
