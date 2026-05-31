# Banking Demo — O11y & Kubernetes Learning Lab

A realistic multi-service banking application built for learning **observability**, **Kubernetes**, and **incident management** with [Resolve](https://resolve.ai). Runs entirely on a laptop via [k3d](https://k3d.io) (k3s in Docker).

---

## What's Inside

10 Python microservices, a React frontend, a chaos engineering service, a full observability stack, and a Resolve satellite — all deployed to Kubernetes via Helm.

### Banking Services

| Service | Responsibility |
|---|---|
| `api-gateway` | Single entry point — routes all external traffic |
| `auth-service` | JWT authentication, user registration & login |
| `customer-service` | Customer profiles & KYC data |
| `account-service` | Bank accounts, balances |
| `transaction-service` | Deposits, withdrawals, transfers |
| `ledger-service` | Double-entry accounting records |
| `fraud-service` | Real-time fraud scoring on every transaction |
| `notification-service` | Transaction alerts & notifications |
| `reporting-service` | Aggregated balance and transaction reports |
| `chaos-service` | Inject latency and errors into any service |
| `frontend` | React UI — accounts, transactions, chaos panel |

### Observability Stack

| Tool | Purpose |
|---|---|
| Prometheus | Metrics scraping from all services + alert rule evaluation + spanmetrics remote-write receiver |
| Alertmanager | Alert routing, deduplication, Slack notifications |
| Loki | Log aggregation |
| Promtail | Ships pod logs to Loki (DaemonSet, static file discovery) |
| Tempo | Distributed trace storage (OTLP HTTP/gRPC) + metrics generator (service graph + spanmetrics) |
| Grafana | 6 pre-provisioned dashboards covering traffic, transactions, fraud, service health, logs, and traces |

### Alert & Log Integrations

Deployed into the `monitoring` namespace, these mirror an enterprise customer's toolchain:

| Component | Purpose |
|---|---|
| `msteams-relay` | Receives Alertmanager webhooks, posts a card to a real Teams webhook (`TEAMS_WEBHOOK_URL`) when set, and always renders a mock `#banking-alerts` channel at :30150 |
| `servicenow-mock` | Receives Alertmanager webhooks and opens/resolves incidents; exposes a ServiceNow-style Table API (`/api/now/table/incident`) and an incident-queue UI at :30140 |
| Elasticsearch + Fluent Bit + Kibana | Fluent Bit ships banking pod logs to a single-node Elasticsearch (index `banking-logs`) in parallel with Loki; Kibana at :30560. Toggle with `elastic.enabled` |

### Resolve Satellite

The Resolve satellite runs in-cluster and connects to `dev0.resolve.ai`. It provides Resolve with:
- **Kubernetes topology** — services, pods, deployments
- **Metrics** — via Prometheus (auto-discovered through Grafana datasource)
- **Logs** — via Loki (auto-discovered through Grafana datasource)
- **Alerts** — via direct Alertmanager integration (polls `/api/v2/alerts/groups`)
- **DNS topology** — via CoreDNS dnstap, showing real-time service-to-service connections

---

## Architecture

```
Browser
  └── frontend :30080  (nginx — also proxies /api/* in-cluster)
        └── api-gateway :30000
              ├── auth-service
              ├── customer-service
              ├── account-service
              ├── transaction-service  ──► ledger-service
              │                        ──► fraud-service
              │                        ──► notification-service
              ├── reporting-service
              └── chaos-service

k3d Cluster (k3s in Docker)
  ├── namespace: banking     ← 10 services + frontend + seeder
  ├── namespace: monitoring  ← Prometheus, Alertmanager, Loki, Promtail, Tempo, Grafana
  └── namespace: default     ← Resolve satellite

CoreDNS dnstap → resolve-satellite:4444
  Gives Resolve real-time service topology from DNS queries
```

**Two namespaces keep monitoring signals clean** — Grafana and Loki live only in `monitoring`, so their own metrics and logs never appear in the banking dashboards.

**Frontend routes API calls through nginx** (`/api/*` → `api-gateway` in-cluster), making the browser→gateway connection visible in Resolve's service topology.

---

## Access Points

| URL | What |
|---|---|
| http://localhost:30080 | React frontend |
| http://localhost:30000 | API gateway (direct) |
| http://localhost:30030 | Grafana — `admin` / `admin` |
| http://localhost:30093 | Alertmanager UI |
| http://localhost:30140 | ServiceNow mock — incident queue |
| http://localhost:30150 | Teams mock — `#banking-alerts` channel view |
| http://localhost:30560 | Kibana — Elastic log destination (index `banking-logs`) |

**Default login:** `sarah.chen@atlasfi.com` / `password123` (and 9 other seeded users)

---

## Prerequisites

| Tool | Install |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Container runtime |
| `k3d` | `brew install k3d` |
| `helm` | `brew install helm` |
| `kubectl` | `brew install kubectl` |
| `jq` | `brew install jq` |
| `make` | Included on macOS |

> **Resource budget:** allocate at least 8 GB RAM to Docker Desktop — **~12 GB with the Elastic stack enabled** (`elastic.enabled: true`, the default). The full stack uses ~4–5 GB under normal load, more under chaos. The Resolve satellite alone requires ~2 GB, and Elasticsearch + Kibana + Fluent Bit add ~2–3 GB. To run lighter, set `elastic.enabled: false` in `helm/monitoring/values.yaml`.

---

## Quick Start

```bash
# 1. Copy .env and add your tokens
cp .env.example .env
# Edit .env — add RESOLVE_INGEST_TOKEN, and optionally SLACK_WEBHOOK_URL
# and/or TEAMS_WEBHOOK_URL (both coexist; Teams falls back to a mock view)

# 2. One command — creates cluster, builds images, deploys everything
make k3d-up
```

The bootstrap script handles everything:
1. Creates the k3d cluster with correct NodePort mappings
2. Builds all Docker images and imports them (no registry needed)
3. Helm-installs the banking app and monitoring stack
4. Generates a Grafana service account token and creates the `resolve-grafana` secret
5. Creates the `alertmanager-slack` and `alertmanager-teams` secrets from `SLACK_WEBHOOK_URL` / `TEAMS_WEBHOOK_URL` (each optional)
6. Deploys the Resolve satellite with Grafana + Alertmanager integrations
7. Patches CoreDNS with dnstap → satellite

**Seed data is automatic.** A `banking-seeder` deployment waits for all services to be healthy and seeds 10 customers, accounts, and transaction history on every startup.

---

## Secrets

Secrets are **never committed to git**. Add them to `.env` — bootstrap reads and provisions them automatically.

```bash
# .env (copy from .env.example)
RESOLVE_INGEST_TOKEN=your-resolve-token
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...   # optional
TEAMS_WEBHOOK_URL=https://...                            # optional (Incoming Webhook / Power Automate)
```

| Secret | Namespace | Used by |
|---|---|---|
| `resolve-ingest-token` | default | Resolve satellite — ingest auth |
| `resolve-grafana` | default | Resolve satellite — Grafana API token (auto-generated) |
| `alertmanager-slack` | monitoring | Alertmanager — Slack webhook |
| `alertmanager-teams` | monitoring | msteams-relay — Teams webhook (optional; mock view if unset) |

---

## Day-to-Day Commands

```bash
# k3d cluster lifecycle
make k3d-up          # full bring-up (cluster + build + deploy)
make k3d-down        # tear down the cluster entirely

# Start/stop a running cluster (faster — no rebuild)
k3d cluster start banking
k3d cluster stop banking

# After starting a stopped cluster — restore kubeconfig
k3d kubeconfig merge banking --kubeconfig-merge-default
kubectl config use-context k3d-banking

# Rebuild after code changes
make k3d-rebuild     # rebuild all images + import + rollout restart
make build-service SVC=fraud-service && make k3d-import  # single service

# Helm upgrades (without rebuilding images)
helm upgrade banking ./helm/banking -n banking
helm upgrade monitoring ./helm/monitoring -n monitoring

# Grafana
make grafana-k8s     # opens http://localhost:30030

# Prometheus direct access
make prometheus-forward  # port-forward to localhost:9090

# Logs
kubectl logs -n banking -l app=fraud-service -f
make promtail-logs   # debug log discovery issues
```

---

## Alerting

### Alert Rules (Prometheus)

| Alert | Condition | Severity | For |
|---|---|---|---|
| `ServiceDown` | `up == 0` | critical | 1m |
| `HighErrorRate` | >5% 5xx | warning | 2m |
| `CriticalErrorRate` | >25% 5xx | critical | 1m |
| `HighLatency` | P95 > 2s | warning | 2m |
| `FraudSpikeDetected` | fraud-service >0.5 req/s | warning | 1m |

### Alertmanager Routing

- **Fan-out:** every alert routes to **Slack** + **Microsoft Teams** (via `msteams-relay`) + **ServiceNow** (incident created in `servicenow-mock`) simultaneously
- **Critical alerts** → 10s group wait
- **Warning alerts** → 30s group wait
- **Inhibition:** `ServiceDown` suppresses `HighErrorRate` + `HighLatency` for the same service
- **Resolved:** automatic follow-up to Slack/Teams and ServiceNow incident moves to Resolved when the alert clears

### Alertmanager UI Filters

```
severity="critical"                    # critical alerts only
job="transaction-service"              # specific service
alertname=~".*ErrorRate"              # pattern match
severity="critical" job="transaction-service"  # combined
```

---

## Generating Signals with Chaos

Use the frontend Chaos Panel at http://localhost:30080 or call the API directly.

### Pre-built Scenarios

```bash
# Payment outage — transaction-service returns ~50% errors
# Triggers: CriticalErrorRate + FraudSpikeDetected (load gen side effect)
curl -X POST http://localhost:30000/chaos/scenarios/payment_outage/trigger

# High latency — 3 second delay on account lookups
# Triggers: HighLatency on account-service
curl -X POST http://localhost:30000/chaos/scenarios/high_latency/trigger

# Cascade failure — transaction + account both degraded
# Triggers: CriticalErrorRate + HighLatency simultaneously
curl -X POST http://localhost:30000/chaos/scenarios/cascade_failure/trigger

# Fraud spike — large transactions to trigger fraud alerts
# Triggers: FraudSpikeDetected
curl -X POST http://localhost:30000/chaos/scenarios/fraud_spike/trigger

# Notification flood — burst of small transactions
# Triggers: HighLatency on notification-service
curl -X POST http://localhost:30000/chaos/scenarios/notification_flood/trigger

# Clear everything
curl -X POST http://localhost:30000/chaos/scenarios/clear
```

### Manual Injection (any service)

```bash
# 60% error rate on a specific service
curl -X POST http://localhost:30000/chaos/inject \
  -H 'Content-Type: application/json' \
  -d '{"service": "fraud-service", "error_rate": 0.6}'

# 2 second latency
curl -X POST http://localhost:30000/chaos/inject \
  -H 'Content-Type: application/json' \
  -d '{"service": "fraud-service", "latency_ms": 2000}'
```

### Simulate a Real Outage

Scale any service to 0 — triggers `ServiceDown [critical]` within 1 minute:
```bash
kubectl scale deployment reporting-service -n banking --replicas=0
# Restore:
kubectl scale deployment reporting-service -n banking --replicas=1
```

> `payment_outage` is the best demo starting point — hits ~50% error rate within seconds, fires `CriticalErrorRate` to Slack in ~1 minute, and shows clearly across the Transaction & Payments dashboard.

---

## Grafana Dashboards

6 dashboards are pre-provisioned in the **Banking** folder at http://localhost:30030.

| Dashboard | What it shows |
|---|---|
| **Banking — Overview** | Service health scorecards, overall RPS/error rate/P95, active alert count |
| **Banking — Transactions & Payments** | transaction-service + ledger deep dive, P50/P95/P99 latency, error logs |
| **Banking — Fraud & Risk** | Fraud check rate with 0.5 req/s threshold line, reporting service panels |
| **Banking — Service Health** | Per-service status with color-coded error rate thresholds, summary table |
| **Banking — Logs Explorer** | Filterable by service and log level — click a `trace_id` to jump to Tempo |
| **Banking — Traces & Service Map** | Service topology graph, trace explorer table, span error rate, P50/P95/P99 from spanmetrics |

---

## Observability Details

### Metrics

Every service exposes `/metrics` in Prometheus format via `prometheus-fastapi-instrumentator`.

Key label convention: `status="2xx"` / `status="5xx"` (not raw status codes).

```promql
# Request rate per service
sum(rate(http_requests_total[1m])) by (job)

# Error rate %
100 * sum by (job) (rate(http_requests_total{status="5xx"}[2m]))
    / sum by (job) (rate(http_requests_total[2m]))

# P95 latency
histogram_quantile(0.95,
  sum by (job, le) (rate(http_request_duration_seconds_bucket[2m]))
)

# Firing alerts
ALERTS{alertstate="firing"}
```

### Logs

All services emit structured JSON via [structlog](https://www.structlog.org):

```json
{
  "level": "info",
  "event": "transaction created",
  "service": "transaction-service",
  "request_id": "a3f1...",
  "trace_id": "00000000...",
  "account_id": "0575d3ec-...",
  "amount": 150.0,
  "timestamp": "2026-04-13T11:02:16.212Z"
}
```

Promtail ships pod logs to Loki with CRI parsing. Full JSON is preserved so `| json` works in LogQL.

```logql
# All errors across services
{namespace="banking"} | json | level="error"

# Fraud events
{namespace="banking", service="fraud-service"} | json | event="fraud alert created"

# Follow a request across all services
{namespace="banking"} | json | request_id="<id>"

# Log volume per service
sum by (service) (count_over_time({namespace="banking"}[1m]))
```

### Tracing

Every service is instrumented with OpenTelemetry (FastAPI + HTTPX auto-instrumentation). Traces export to Tempo via OTLP HTTP. Each log line includes a `trace_id` field — clicking it in the Logs Explorer dashboard opens the full trace in Tempo.

Tempo's **metrics generator** derives two sets of Prometheus metrics from incoming spans and remote-writes them:

- `traces_service_graph_*` — request/error counts and latency between service pairs, used by the service map
- `traces_spanmetrics_*` — per-operation call counts and latency histograms, used by the latency panels

```promql
# Request rate from spans (server-side)
rate(traces_spanmetrics_calls_total{span_kind="SPAN_KIND_SERVER"}[2m])

# P99 latency from spans
histogram_quantile(0.99, rate(traces_spanmetrics_latency_bucket{span_kind="SPAN_KIND_SERVER"}[2m]))

# Span error rate
rate(traces_spanmetrics_calls_total{status_code="STATUS_CODE_ERROR"}[2m])
  / rate(traces_spanmetrics_calls_total[2m])
```

The OTLP endpoint is set in `helm/banking/values.yaml`:
```yaml
otelEndpoint: "http://tempo.monitoring.svc.cluster.local:4318"
```

---

## Project Layout

```
banking/
├── .env.example                       # copy to .env — add tokens here
├── Makefile
├── scripts/
│   └── bootstrap-k3d.sh              # one-command cluster + deploy + secrets
│
├── base/                              # shared Python base image
│   ├── Dockerfile
│   └── requirements.txt
│
├── shared/                            # library copied into every service
│   ├── observability.py               # logging + tracing + Prometheus
│   ├── database.py
│   ├── chaos.py
│   └── http_client.py
│
├── services/
│   ├── api-gateway/
│   ├── auth-service/
│   └── ...                            # one directory per service
│
├── frontend/                          # React app + nginx config
│
├── seed/
│   └── seed.py                        # populates test data (runs automatically)
│
└── helm/
    ├── banking/                       # Helm chart — services + frontend + seeder
    │   ├── values.yaml
    │   ├── resolve-values.yaml        # Resolve satellite config (no secrets)
    │   └── templates/
    │       └── seed-job.yaml          # seeder Deployment — auto-seeds on every start
    ├── monitoring/                    # Helm chart — full o11y stack
    │   ├── values.yaml
    │   ├── dashboards/                # 6 Grafana dashboard JSON files
    │   └── templates/
    │       ├── prometheus/            # Recreate strategy, alert rules, remote-write receiver
    │       ├── alertmanager/          # Routing, Slack receiver, inhibition rules
    │       ├── loki/
    │       ├── promtail/
    │       ├── tempo/                 # OTLP receiver, metrics generator, local storage
    │       └── grafana/
    └── satellite-chart/               # Vendored Resolve satellite Helm chart
```

---

## Adding a New Service

1. Create `services/my-service/` with `main.py`, `Dockerfile`, `requirements.txt`
2. Wire in the shared factory:
   ```python
   import sys
   sys.path.insert(0, "/app/shared")
   from observability import create_app, get_logger

   log = get_logger()
   app = create_app("My Service")
   ```
3. Add to `SERVICES` in `Makefile` and `scripts/bootstrap-k3d.sh`
4. Add to `helm/banking/templates/services.yaml` and `values.yaml`
5. Add a scrape target to `helm/monitoring/templates/prometheus/configmap.yaml`

You get `/health`, `/ready`, `/metrics`, structured JSON logging, and tracing automatically.

---

## Troubleshooting

**Kubeconfig lost after Docker Desktop restart**
```bash
k3d kubeconfig merge banking --kubeconfig-merge-default
kubectl config use-context k3d-banking
```

**Pods stuck in `ImagePullBackOff`**

Images are built locally and imported directly into k3d — no registry needed. Rebuild and re-import:
```bash
make k3d-rebuild
```

**Grafana shows "No data"**
```bash
# Check Prometheus targets
make prometheus-forward
open http://localhost:9090/targets

# Check Promtail is shipping logs
make promtail-logs
```

**Seed data missing after restart**

The `banking-seeder` deployment handles this automatically. Check its status:
```bash
kubectl get pods -n banking | grep seeder
kubectl logs -n banking -l app=banking-seeder -c seeder
```

**Prometheus stuck in CrashLoopBackOff after restart**

Prometheus uses `Recreate` strategy to avoid PVC lock conflicts. If you see two Prometheus pods:
```bash
kubectl rollout undo deployment/prometheus -n monitoring
```

**Resolve satellite not showing alerts**
```bash
# Verify Alertmanager integration is polling
kubectl logs -n default resolve-satellite-satellite-chart-0 | grep alertManager

# Verify alerts are firing in Prometheus
kubectl exec -n monitoring deploy/prometheus -- \
  wget -qO- 'http://localhost:9090/api/v1/alerts' | python3 -m json.tool
```

**Out of disk space**
```bash
docker system prune -f
```
