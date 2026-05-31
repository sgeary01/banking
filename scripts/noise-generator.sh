#!/usr/bin/env bash
#
# Generates a realistic on-call noise floor for the Atlas Financial demo:
#   - Frequent warning-level chaos that fires/resolves on a short cycle
#   - Occasional sustained critical events that demand investigation
#
# Discovers scenarios from /chaos/scenarios at startup so the same script
# works on `main` (banking) and `insurance` branches without modification.
#
# Tunables (env vars):
#   NOISE_BASE     mean seconds between warning chaos kicks (default 120)
#   NOISE_JITTER   added 0..N seconds of jitter           (default 60)
#   CRISIS_BASE    mean seconds between critical events   (default 900 = 15min)
#   CRISIS_JITTER  added 0..N seconds of jitter           (default 300)
#   NOISE_DURATION seconds each warning runs              (default 120)
#   CRISIS_DURATION seconds each critical runs            (default 150)
#   DURATION       total run time, 0 = forever            (default 0)
#
# Ctrl-C exits cleanly: restores any scaled-down services + clears chaos state.

set -u
GW=${GW:-http://localhost:30000}
KCTX=${KCTX:-k3d-banking}
K="kubectl --context $KCTX"

NOISE_BASE=${NOISE_BASE:-120}
NOISE_JITTER=${NOISE_JITTER:-60}
CRISIS_BASE=${CRISIS_BASE:-900}
CRISIS_JITTER=${CRISIS_JITTER:-300}
NOISE_DURATION=${NOISE_DURATION:-120}
CRISIS_DURATION=${CRISIS_DURATION:-150}
DURATION=${DURATION:-0}

# Discover available chaos scenarios from the running cluster.
SCENARIOS_JSON=$(curl -s "$GW/chaos/scenarios" 2>/dev/null || echo "[]")
mapfile -t ALL_SCENARIOS < <(echo "$SCENARIOS_JSON" | python3 -c "
import json,sys
try: [print(s['name']) for s in json.load(sys.stdin)]
except: pass" 2>/dev/null)

if (( ${#ALL_SCENARIOS[@]} == 0 )); then
  echo "could not discover chaos scenarios at $GW/chaos/scenarios — is the cluster up?" >&2
  exit 1
fi

# Classify by name. _outage / _latency / cascade get treated as crisis material.
# Everything else (spikes, floods) is warning-flap material.
CRISIS_CHAOS=()
WARNING_CHAOS=()
for s in "${ALL_SCENARIOS[@]}"; do
  case "$s" in
    *outage*|*latency*|cascade*) CRISIS_CHAOS+=("$s") ;;
    *) WARNING_CHAOS+=("$s") ;;
  esac
done

# Crisis can also scale a service to 0 → ServiceDown fires in ~60s
SCALE_TARGETS=(reporting-service notification-service)

ts() { date +%H:%M:%S; }
log() { printf "[%s] %s\n" "$(ts)" "$*"; }

cleanup() {
  echo
  log "stopping — restoring services and clearing chaos..."
  for svc in "${SCALE_TARGETS[@]}"; do
    $K scale deploy/$svc -n banking --replicas=1 >/dev/null 2>&1 || true
  done
  curl -s -X POST "$GW/chaos/scenarios/clear" >/dev/null 2>&1 || true
  log "clean."
  exit 0
}
trap cleanup INT TERM

# Run a chaos scenario in a background subshell for `dur` seconds, then clear.
run_chaos() {
  local name=$1 dur=$2
  ( END=$((SECONDS+dur)); while [ $SECONDS -lt $END ]; do
      curl -s -X POST "$GW/chaos/scenarios/$name/trigger" >/dev/null 2>&1
      sleep 6
    done
    curl -s -X POST "$GW/chaos/scenarios/clear" >/dev/null 2>&1
  ) &
}

warning_flap() {
  if (( ${#WARNING_CHAOS[@]} == 0 )); then return; fi
  local s="${WARNING_CHAOS[$RANDOM % ${#WARNING_CHAOS[@]}]}"
  log "warning flap: $s (${NOISE_DURATION}s)"
  run_chaos "$s" "$NOISE_DURATION"
}

critical_event() {
  # 50/50: kubectl scale-down OR sustained chaos
  if (( RANDOM % 2 == 0 )) && (( ${#SCALE_TARGETS[@]} > 0 )); then
    local svc="${SCALE_TARGETS[$RANDOM % ${#SCALE_TARGETS[@]}]}"
    log "CRITICAL: scaling $svc to 0 for ${CRISIS_DURATION}s"
    $K scale deploy/$svc -n banking --replicas=0 >/dev/null
    ( sleep "$CRISIS_DURATION"
      $K scale deploy/$svc -n banking --replicas=1 >/dev/null
      log "  $svc restored"
    ) &
  elif (( ${#CRISIS_CHAOS[@]} > 0 )); then
    local s="${CRISIS_CHAOS[$RANDOM % ${#CRISIS_CHAOS[@]}]}"
    log "CRITICAL: sustained $s for ${CRISIS_DURATION}s"
    run_chaos "$s" "$CRISIS_DURATION"
  fi
}

start=$SECONDS
last_crisis=$start
next_noise=$start

log "noise generator running."
log "  warnings: ${WARNING_CHAOS[*]:-(none)}"
log "  crises:   ${CRISIS_CHAOS[*]:-(none)} | scale: ${SCALE_TARGETS[*]}"
log "  cadence:  noise every ${NOISE_BASE}s ±${NOISE_JITTER}, crisis every ${CRISIS_BASE}s ±${CRISIS_JITTER}"
log "  Ctrl-C to stop. State restored on exit."

while :; do
  now=$SECONDS

  if (( now - last_crisis > CRISIS_BASE + RANDOM % CRISIS_JITTER )); then
    critical_event
    last_crisis=$now
  fi

  if (( now >= next_noise )); then
    warning_flap
    next_noise=$((now + NOISE_BASE + RANDOM % NOISE_JITTER))
  fi

  if (( DURATION > 0 && now - start >= DURATION )); then
    log "duration $DURATION s elapsed."
    cleanup
  fi

  sleep 5
done
