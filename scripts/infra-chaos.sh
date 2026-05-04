#!/usr/bin/env bash
# infra-chaos.sh — Infrastructure-level chaos scenarios for the banking demo.
#
# These simulate real operational incidents that are NOT tied to the chaos
# service — they look like genuine infrastructure or configuration failures.
#
# Usage:
#   ./scripts/infra-chaos.sh <scenario> [trigger|clear]
#   ./scripts/infra-chaos.sh clear-all
#
# Scenarios:
#   oom          OOM kill — patches transaction-service memory limit to 48Mi
#   jwt          JWT secret rotation gone wrong — api-gateway rejects all tokens
#   netpolicy    Network blackout — blocks ingress to fraud-service
#   cpu          CPU starvation — throttles account-service to 10m CPU
#   deployment   Bad deployment — rolls out a broken image on reporting-service
#   clear-all    Removes all infra chaos at once

set -euo pipefail

NAMESPACE=banking
ORIGINAL_MEMORY_LIMIT="192Mi"
ORIGINAL_CPU_LIMIT="250m"
JWT_SECRET="dev-secret-change-in-prod"

# ── Helpers ────────────────────────────────────────────────────────────────────

usage() {
  grep '^#' "$0" | grep -v '#!/' | sed 's/^# \{0,1\}//'
  exit 0
}

patch_deployment() {
  local deploy=$1 path=$2 value=$3
  kubectl patch deployment "$deploy" -n "$NAMESPACE" --type=json \
    -p="[{\"op\":\"replace\",\"path\":\"$path\",\"value\":\"$value\"}]"
}

wait_rollout() {
  local deploy=$1
  echo "  Waiting for $deploy rollout..."
  kubectl rollout status deployment/"$deploy" -n "$NAMESPACE" --timeout=90s
}

# ── Scenario: OOM Kill ─────────────────────────────────────────────────────────
# Patches transaction-service memory limit to 48Mi. Under load (run a few
# transactions) the kubelet OOM-kills the container. You see pod restarts spike
# in the K8s dashboard without any application-level error logs.

oom_trigger() {
  echo "🔴 OOM: patching transaction-service memory limit → 90Mi (tight enough to OOM under load)"
  kubectl patch deployment transaction-service -n "$NAMESPACE" --type=json -p='[
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"64Mi"},
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"90Mi"}
  ]'
  wait_rollout transaction-service
  echo ""
  echo "  transaction-service is running but memory-constrained."
  echo "  Generate load to trigger the OOM kill:"
  echo "    for i in \$(seq 1 50); do curl -s -o /dev/null http://localhost:30000/transactions/health; done"
  echo ""
  echo "  Watch: kubectl get pods -n banking -w"
  echo "  Signals: K8s dashboard → pod restarts spike, container memory % → 100%"
}

oom_clear() {
  echo "✅ OOM: restoring transaction-service memory limits"
  kubectl patch deployment transaction-service -n "$NAMESPACE" --type=json -p='[
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/requests/memory","value":"96Mi"},
    {"op":"replace","path":"/spec/template/spec/containers/0/resources/limits/memory","value":"192Mi"}
  ]'
  wait_rollout transaction-service
}

# ── Scenario: JWT Secret Rotation Gone Wrong ───────────────────────────────────
# Sets a wrong JWT_SECRET on the api-gateway only. Auth-service still issues
# tokens signed with the real secret, but api-gateway rejects them all with 401.
# No 5xx errors — the existing HighErrorRate alert stays silent. Requires
# looking at 4xx rate or auth logs to diagnose.

jwt_trigger() {
  echo "🔴 JWT: setting wrong JWT_SECRET on api-gateway"
  kubectl set env deployment/api-gateway -n "$NAMESPACE" \
    JWT_SECRET=wrong-secret-rotation-failed
  wait_rollout api-gateway
  echo ""
  echo "  All authenticated requests now return 401."
  echo "  Signals: HighClientErrorRate alert fires, auth-service looks healthy"
  echo "  Red herring: auth-service /health is green, no 5xx errors anywhere"
}

jwt_clear() {
  echo "✅ JWT: restoring correct JWT_SECRET on api-gateway"
  kubectl set env deployment/api-gateway -n "$NAMESPACE" \
    JWT_SECRET="$JWT_SECRET"
  wait_rollout api-gateway
}

# ── Scenario: Network Policy — Dependency Blackout ────────────────────────────
# Applies a NetworkPolicy that blocks all ingress to fraud-service.
# transaction-service calls fraud-service on every transaction — those calls
# now time out. Transactions fail but fraud-service reports itself healthy.
# Classic "my service is fine" — broken edge only visible in Tempo service map.

netpolicy_trigger() {
  echo "🔴 NETPOLICY: blocking ingress to fraud-service"
  kubectl apply -f - <<EOF
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
  echo ""
  echo "  fraud-service is now unreachable from transaction-service."
  echo "  Signals: CriticalErrorRate on transaction-service, Tempo service map shows broken edge"
  echo "  Red herring: fraud-service /health returns 200, no restarts"
}

netpolicy_clear() {
  echo "✅ NETPOLICY: removing network policy"
  kubectl delete networkpolicy infra-chaos-block-fraud -n "$NAMESPACE" --ignore-not-found
}

# ── Scenario: CPU Starvation ───────────────────────────────────────────────────
# Patches account-service CPU limit to 10m. Under any load the container is
# heavily throttled. No errors — just latency. HighLatency alert fires but
# the root cause (CPU throttle rate) only visible in the K8s dashboard cAdvisor
# panels, not the application metrics.

cpu_trigger() {
  echo "🔴 CPU: throttling account-service CPU limit → 10m"
  patch_deployment account-service \
    /spec/template/spec/containers/0/resources/limits/cpu 10m
  wait_rollout account-service
  echo ""
  echo "  account-service will be heavily CPU-throttled under any load."
  echo "  Signals: HighLatency alert fires, K8s dashboard → CPU throttle rate spikes"
  echo "  Red herring: no errors, service appears healthy, restarts=0"
}

cpu_clear() {
  echo "✅ CPU: restoring account-service CPU limit → $ORIGINAL_CPU_LIMIT"
  patch_deployment account-service \
    /spec/template/spec/containers/0/resources/limits/cpu "$ORIGINAL_CPU_LIMIT"
  wait_rollout account-service
}

# ── Scenario: Bad Deployment ───────────────────────────────────────────────────
# Patches reporting-service to use a non-existent image tag. Kubernetes starts
# a rolling update — new pods go into ImagePullBackOff. Old pods keep running
# so the service stays ~50% degraded rather than fully down.
# DeploymentReplicasMismatch alert fires; visible in K8s dashboard replica panel.

deployment_trigger() {
  echo "🔴 DEPLOYMENT: rolling out broken image tag on reporting-service"
  patch_deployment reporting-service \
    /spec/template/spec/containers/0/image banking/reporting-service:broken-v2
  echo ""
  echo "  New pods will fail ImagePullBackOff. Old pod keeps serving (partial degradation)."
  echo "  Signals: DeploymentReplicasMismatch alert, K8s dashboard → replicas mismatch"
  echo "  Red herring: reporting-service still responds (old pod), metrics look normal"
  echo ""
  echo "  Watch: kubectl get pods -n banking -w"
}

deployment_clear() {
  echo "✅ DEPLOYMENT: rolling back reporting-service image"
  patch_deployment reporting-service \
    /spec/template/spec/containers/0/image banking/reporting-service:latest
  wait_rollout reporting-service
}

# ── Clear All ──────────────────────────────────────────────────────────────────

clear_all() {
  echo "🧹 Clearing all infra chaos..."
  oom_clear       2>/dev/null || true
  jwt_clear       2>/dev/null || true
  netpolicy_clear 2>/dev/null || true
  cpu_clear       2>/dev/null || true
  deployment_clear 2>/dev/null || true
  echo "✅ All infra chaos cleared."
}

# ── Dispatch ───────────────────────────────────────────────────────────────────

SCENARIO=${1:-}
ACTION=${2:-trigger}

case "$SCENARIO" in
  oom)        oom_${ACTION} ;;
  jwt)        jwt_${ACTION} ;;
  netpolicy)  netpolicy_${ACTION} ;;
  cpu)        cpu_${ACTION} ;;
  deployment) deployment_${ACTION} ;;
  clear-all)  clear_all ;;
  help|--help|-h|"") usage ;;
  *) echo "Unknown scenario: $SCENARIO"; usage ;;
esac
