# HANDOFF — Atlas Financial demo prep

_As of 2026-05-30. Demo date: **2026-06-02**._

Read this cold to pick up the work in a fresh Claude Code / CLI window. The durable
state is the **repo** (this dir) + the **running k3d cluster** — both are shared across
any window. Nothing to merge.

## What this is
The `banking` O11y lab, tweaked for the Atlas Financial demo. Goal: an injected incident flows
through the customer's toolchain — alerts fan out to **Microsoft Teams** + **ServiceNow** (added
alongside the existing Slack path), logs land in **Elastic**, and the Resolve satellite runs RCA.
Full design + rationale: `~/.claude/plans/floating-wishing-fox.md`.

## Current state: DEPLOYED and running
- k3d cluster `banking` is up; kube-context `k3d-banking`.
- All 12 banking pods Ready; all monitoring pods Ready (incl. elasticsearch, kibana, fluent-bit, msteams-relay, servicenow-mock).
- Resolve satellite Running in `default`, connected to dev0.resolve.ai.
- `.env` has RESOLVE_INGEST_TOKEN + SLACK_WEBHOOK_URL (real). `TEAMS_WEBHOOK_URL` is **blank**
  → Teams relay renders its mock channel view only. Set it to a real Incoming Webhook / Power
  Automate URL to post to a real Teams channel, then re-run bootstrap (or recreate the
  `alertmanager-teams` secret + restart `msteams-relay`).

## URLs / login
| URL | What |
|---|---|
| http://localhost:30080 | Atlas Financial app — **login `sarah.chen@atlasfi.com` / `password123`** |
| http://localhost:30030 | Grafana (admin/admin) — has Prometheus, Loki, Tempo, **Elasticsearch** datasources |
| http://localhost:30093 | Alertmanager |
| http://localhost:30140 | ServiceNow mock — incident queue UI + `/api/now/table/incident` |
| http://localhost:30150 | Teams mock — `#atlas-app-alerts` channel + `/api/messages` |
| http://localhost:30560 | Kibana (Elastic, index `banking-logs`) |
| http://localhost:30000/docs | API gateway |

## What changed (high level)
- New services `services/msteams-relay/` + `services/servicenow-mock/` (FastAPI on shared base), deployed into the `monitoring` namespace via new templates under `helm/monitoring/templates/{msteams-relay,servicenow-mock}/`.
- Alertmanager `helm/monitoring/templates/alertmanager/configmap.yaml`: each receiver keeps `slack_configs` and now also `webhook_configs` → Teams relay + ServiceNow mock (`send_resolved: true`).
- Elastic: `helm/monitoring/templates/{elasticsearch,kibana,fluent-bit}/` + ES datasource in grafana datasources configmap. `elastic.enabled: true` by default (values.yaml). Set `elastic.enabled: false` to run light.
- Build/deploy wiring: `Makefile` + `scripts/bootstrap-k3d.sh` SERVICES include the two new services; bootstrap adds k3d NodePorts 30140/30150/30560, an `alertmanager-teams` secret, and a namespace-with-Helm-ownership fix (see below).
- Reskin: frontend chrome → Atlas Financial (accent `#1E40AF`), `helm/banking/seed/seed.py` customers → `@atlasfi.com` emails with neutral addresses. Auth + seed *logic* untouched.

## Fixes already applied during bring-up
1. **Helm v4 namespace adoption** — bootstrap pre-created `monitoring` ns with plain kubectl; Helm v4 refused to import it. Fixed: bootstrap now applies the namespace with `app.kubernetes.io/managed-by: Helm` + `meta.helm.sh/release-{name,namespace}` annotations. (In `scripts/bootstrap-k3d.sh`.)
2. **fluent-bit crashloop** — its position DB pointed at the read-only `/var/log` mount. Fixed in chart (`helm/monitoring/templates/fluent-bit/`): DB moved to a writable `state` emptyDir at `/var/lib/fluent-bit`. Already live-patched into the cluster AND fixed in the chart, so re-runs are clean.

## KNOWN ISSUE — scenarios don't self-fire alerts (the one real to-do)
`payment_outage` / `cascade_failure` inject a *persistent* error rate but only generate a
~6-second load burst (60 tx @ 0.1s in `services/chaos-service/main.py` `_generate_transactions`).
`CriticalErrorRate` needs >25% 5xx **sustained for 1m**, so with no ongoing traffic the rate
decays to 0 and nothing fires. Confirmed: transaction-service error ratio returns to 0 after the burst.

**Intended fix** (do this in the permissive CLI window):
- In `services/chaos-service/main.py`: add `"duration_s": 180` to `payment_outage` and `cascade_failure`; make `_generate_transactions` loop until `duration_s` elapsed (~3 tx/s, re-picking accounts) when set, else fall back to `count`. Pass `duration_s` through from `trigger_scenario`.
- Rebuild just that service:
  ```bash
  make build-service SVC=chaos-service && make k3d-import
  kubectl rollout restart deploy/chaos-service -n banking
  ```
- Verify: trigger `payment_outage`, wait ~90s, confirm `CriticalErrorRate` firing in Prometheus/Alertmanager → Teams card (:30150) + ServiceNow incident (:30140).

**Reliable demo trigger that works RIGHT NOW (no code change, no traffic needed):** scale a
service to 0 → `ServiceDown [critical]` fires in 1m → fans out to Slack + Teams + ServiceNow:
```bash
kubectl scale deployment reporting-service -n banking --replicas=0   # fire
kubectl scale deployment reporting-service -n banking --replicas=1   # clear
```
For the error-rate scenarios pre-fix, drive sustained load (re-trigger every ~6s for ~2m) or use `/tmp/verify_chain.sh`.

## Verification status (task #7)
- Static: helm lint/template both charts, py_compile services, bash -n bootstrap, alertmanager.yml parses with slack+teams+servicenow — all PASS.
- Live: **PASS (with sustained load).** Drove load via `/tmp/verify_chain.sh`; `CriticalErrorRate`
  fired after ~85s and fanned out to all three:
  - Alertmanager: `CriticalErrorRate [critical]` active
  - ServiceNow: `INC0010001 | 1 - Critical | New | transaction-service`
  - Teams (mock): `🔴 [FIRING] CriticalErrorRate`
  - Elastic `banking-logs`: ~11k docs (Fluent Bit shipping confirmed)
- The ONLY gap is self-firing scenarios (see Known Issue) — the pipeline itself is fully working.

## Common commands
```bash
kubectl config use-context k3d-banking
kubectl get pods -A
make -C ~/gitrepos/resolve/banking k3d-rebuild     # rebuild all + reimport + restart
./scripts/bootstrap-k3d.sh --no-build               # re-run deploy without rebuilding images
k3d cluster stop banking / start banking            # pause/resume to save resources
```

## Running this window with fewer prompts
Start the CLI in this repo with relaxed permissions for the rebuild/verify loop:
```bash
cd ~/gitrepos/resolve/banking
claude --dangerously-skip-permissions     # disposable local cluster — fine here
# or: claude --permission-mode acceptEdits
```
(Sean also wants to revisit the `fewer-permission-prompts` skill to set a persistent allowlist across sessions — separate follow-up.)
