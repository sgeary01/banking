# Banking Demo — O11y & Kubernetes Learning Lab

A realistic multi-service banking application built for learning **observability**, **Kubernetes**, and **incident management** with [Resolve](https://resolve.io). Runs entirely on a laptop.

---

## What's Inside

10 Python microservices, a React frontend, a chaos engineering service, and a full observability stack — all deployed to Kubernetes via Helm.

### Services

| Service | NodePort | Responsibility |
|---|---|---|
| `api-gateway` | 30000 | Single entry point — routes all external traffic |
| `auth-service` | — | JWT authentication, user registration & login |
| `customer-service` | — | Customer profiles & KYC data |
| `account-service` | — | Bank accounts, balances |
| `transaction-service` | — | Deposits, withdrawals, transfers — the core flow |
| `ledger-service` | — | Double-entry accounting records |
| `fraud-service` | — | Real-time fraud scoring on every transaction |
| `notification-service` | — | Transaction alerts & notifications |
| `reporting-service` | — | Aggregated balance and transaction reports |
| `chaos-service` | — | Inject latency and errors into any service |
| `frontend` | 30080 | React UI — accounts, transactions, chaos panel |

> Internal services are only reachable within the cluster. All external traffic goes through the api-gateway at port 30000.

### Observability Stack

| Tool | NodePort | Purpose |
|---|---|---|
| Grafana | 30030 | Dashboards — pre-provisioned Banking Overview |
| Prometheus | — (ClusterIP) | Metrics scraping from all 10 services |
| Loki | — (ClusterIP) | Log aggregation |
| Promtail | — (DaemonSet) | Ships pod logs to Loki via Kubernetes SD |

---

## Architecture

```
Browser
  └── frontend :30080
        └── api-gateway :30000
              ├── auth-service
              ├── customer-service
              ├── account-service
              ├── transaction-service  ──► ledger-service
              │                        ──► fraud-service
              │                        ──► notification-service
              ├── reporting-service
              └── chaos-service

Kubernetes Cluster (orbstack)
  ├── namespace: banking     ← all 10 services + frontend
  └── namespace: monitoring  ← Prometheus, Loki, Promtail, Grafana
        Prometheus scrapes banking services via cluster-internal DNS
        Promtail discovers banking pods via Kubernetes SD
        Grafana queries Prometheus + Loki — never touches the banking network directly
```

**Two namespaces keep monitoring signals clean.** Grafana and Loki only exist in `monitoring` — their own metrics and logs never appear in the banking dashboards.

---

## Prerequisites

| Tool | Install |
|---|---|
| [OrbStack](https://orbstack.dev) | Recommended Docker + K8s runtime for Mac (lighter than Docker Desktop) |
| `helm` | `brew install helm` |
| `kubectl` | Included with OrbStack |
| `make` | Included on macOS |

> **Resource budget:** the full stack uses ~3 GB RAM and ~4 CPU cores under load. Tested on a MacBook with 24 GB RAM.

---

## Quick Start

```bash
# 1. Build all images (~3 min on first run, fast after that)
make build

# 2. Deploy banking app to Kubernetes
make helm-install

# 3. Deploy monitoring stack to Kubernetes
make monitoring-helm-install

# 4. Seed realistic test data (runs as a K8s Job automatically on helm-install,
#    but run manually if needed)
make seed
```

Then open:

| URL | What you'll see |
|---|---|
| http://localhost:30080 | React frontend — login with `alice@example.com` / `password123` |
| http://localhost:30030 | Grafana — `admin` / `admin` |

---

## Day-to-Day Commands

```bash
# Kubernetes — banking app
make helm-install          # deploy or upgrade banking app
make helm-uninstall        # remove banking app from cluster

# Kubernetes — monitoring
make monitoring-helm-install    # deploy or upgrade monitoring stack
make monitoring-helm-uninstall  # remove monitoring from cluster

# Building
make build                         # rebuild all images
make build-service SVC=fraud-service  # rebuild one service

# Logs (kubectl)
kubectl logs -n banking -l app=fraud-service -f
kubectl logs -n monitoring -l app=promtail -f

# Debugging
make promtail-logs         # tail Promtail — useful for log discovery issues
make prometheus-forward    # port-forward Prometheus to localhost:9090

# Open Grafana
make grafana-k8s           # opens http://localhost:30030

# Docker Compose (local dev / fast iteration)
make up                    # start banking app in Compose
make down                  # stop Compose app
make monitoring-up         # start monitoring in Compose
make monitoring-down       # stop Compose monitoring
make seed                  # seed test data (works for both K8s and Compose)

# Cleanup
make clean                 # remove all built images
```

---

## Generating Signals with Chaos

The chaos service lets you inject faults from the frontend Chaos Panel or directly via the API.

### Pre-built Scenarios

Scenarios auto-discover seeded accounts and generate a burst of real transactions — errors appear in Grafana within seconds, no manual traffic generation needed.

```bash
# Payment outage — transaction-service returns 50% errors
curl -X POST http://localhost:30000/chaos/scenarios/payment_outage/trigger

# Slow accounts — 3 second latency on all account lookups
curl -X POST http://localhost:30000/chaos/scenarios/high_latency/trigger

# Cascade failure — transaction + account both degraded
curl -X POST http://localhost:30000/chaos/scenarios/cascade_failure/trigger

# Fraud spike — high-value transactions to trigger fraud alerts
curl -X POST http://localhost:30000/chaos/scenarios/fraud_spike/trigger

# Notification flood — burst of small transactions
curl -X POST http://localhost:30000/chaos/scenarios/notification_flood/trigger

# Clear all chaos
curl -X POST http://localhost:30000/chaos/scenarios/clear
```

### Manual Injection

```bash
# 30% error rate on ledger-service
curl -X POST http://localhost:30000/chaos/inject \
  -H 'Content-Type: application/json' \
  -d '{"service": "ledger-service", "error_rate": 0.3}'

# 2 second latency on fraud checks
curl -X POST http://localhost:30000/chaos/inject \
  -H 'Content-Type: application/json' \
  -d '{"service": "fraud-service", "latency_ms": 2000}'
```

---

## Observability Details

### Metrics

Every service exposes `/metrics` in Prometheus format via `prometheus-fastapi-instrumentator`. Key queries:

```promql
# Request rate per service
sum(rate(http_requests_total[1m])) by (job)

# Error rate %
100 * (sum(rate(http_requests_total{status="5xx"}[5m])) or vector(0))
    / sum(rate(http_requests_total[5m]))

# P95 latency
histogram_quantile(0.95,
  sum(rate(http_request_duration_seconds_bucket[1m])) by (job, le)
)

# Services currently up
count(up{job=~"api-gateway|auth-service|..."} == 1)
```

> **Note:** the status label is `status="2xx"` / `status="5xx"` (not `status_code`).

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

Promtail ships pod logs to Loki using Kubernetes Service Discovery — it automatically picks up any pod in the `banking` namespace. Every log line carries `request_id` and `trace_id` for cross-service correlation.

Useful LogQL queries in Grafana:

```logql
# All errors across services
{service=~".+"} | json | level="error"

# Fraud alerts
{service="fraud-service"} | json | event="fraud alert"

# Follow a single request across all services
{service=~".+"} | json | request_id="<id>"
```

### Tracing

OpenTelemetry SDK is wired into every service (FastAPI + HTTPX instrumented). Traces are silently dropped until you point `OTEL_EXPORTER_OTLP_ENDPOINT` at a collector (Tempo, Jaeger, etc.):

```yaml
# In helm/banking/values.yaml:
otelEndpoint: "http://tempo.monitoring.svc.cluster.local:4318"
```

---

## Grafana Dashboard

The **Banking Services Overview** dashboard is pre-provisioned — no import needed. Open http://localhost:30030.

| Panel | What it shows |
|---|---|
| Total Requests | Aggregate request count over the last 5 min |
| Error Rate % | Global 5xx rate — 0% when healthy, spikes under chaos |
| Services Up | Count of healthy services (should be 10) |
| Requests/sec per Service | Per-service throughput time series |
| Error Rate per Service | Per-service 5xx rate — isolates the broken service |
| P95 Latency per Service | Tail latency — shows latency injection clearly |
| Banking Service Logs | Live log stream from all services |

Datasource UIDs are pinned (`banking-prometheus`, `banking-loki`) so dashboards survive pod restarts without breaking.

---

## Project Layout

```
banking/
├── Makefile                          # all common tasks
├── docker-compose.yml                # banking app (local dev)
├── docker-compose.monitoring.yml     # monitoring stack (local dev)
│
├── base/                             # shared Python base image
│   ├── Dockerfile
│   └── requirements.txt              # FastAPI, structlog, OTEL, SQLAlchemy, ...
│
├── shared/                           # library copied into every service container
│   ├── observability.py              # logging + tracing + Prometheus wiring
│   ├── database.py                   # SQLAlchemy setup
│   ├── chaos.py                      # in-process chaos state store
│   └── http_client.py                # instrumented HTTPX client
│
├── services/
│   ├── api-gateway/
│   ├── auth-service/
│   ├── account-service/
│   ├── transaction-service/
│   └── ...                           # one directory per service
│
├── frontend/                         # React app
├── seed/                             # seed.py — populates test data
│
├── helm/
│   ├── banking/                      # Helm chart — 10 services + frontend
│   │   ├── Chart.yaml
│   │   ├── values.yaml
│   │   └── templates/
│   └── monitoring/                   # Helm chart — Prometheus, Loki, Promtail, Grafana
│       ├── Chart.yaml
│       ├── values.yaml
│       ├── dashboards/banking-overview.json
│       └── templates/
│           ├── prometheus/
│           ├── loki/
│           ├── promtail/             # DaemonSet + RBAC for K8s log discovery
│           └── grafana/
│
└── monitoring/                       # Config files for Docker Compose monitoring
    ├── prometheus/prometheus.yml
    ├── loki/loki-config.yml
    ├── promtail/promtail-config.yml
    └── grafana/provisioning/
```

---

## Adding a New Service

1. Create `services/my-service/` with `main.py`, `Dockerfile`, `requirements.txt`
2. In `main.py`, use the shared factory:
   ```python
   import sys
   sys.path.insert(0, "/app/shared")
   from observability import create_app, get_logger

   log = get_logger()
   app = create_app("My Service")
   ```
3. In the `Dockerfile`:
   ```dockerfile
   ARG BASE_IMAGE=banking/base:latest
   FROM ${BASE_IMAGE}
   COPY shared/ /app/shared/
   COPY services/my-service/ .
   ```
4. Add to `helm/banking/templates/services.yaml` and `helm/banking/values.yaml`
5. Add a scrape target to `helm/monitoring/templates/prometheus/configmap.yaml`
6. Add to `SERVICES` in `Makefile`

You get `/health`, `/ready`, `/metrics`, structured JSON logging, and tracing for free.

---

## Connecting to Resolve

Once the stack is running, install the [Resolve Satellite](https://docs.resolve.ai/resolve-satellite) into the cluster:

```bash
helm install resolve-satellite <resolve-chart> \
  --namespace resolve --create-namespace \
  --values resolve-values.yaml
```

Point it at the in-cluster monitoring URLs:
- Prometheus: `http://prometheus.monitoring.svc.cluster.local:9090`
- Loki: `http://loki.monitoring.svc.cluster.local:3100`

The `payment_outage` chaos scenario is the most dramatic starting point — transaction-service hits ~50% error rate within seconds, generating clear signal for Resolve to surface.

---

## Troubleshooting

**Pods stuck in `ImagePullBackOff`**

Images are built locally and not pushed to a registry. Make sure `imagePullPolicy: IfNotPresent` is set (it is, by default) and rebuild:
```bash
make build && make helm-install
```

**Grafana shows "No data"**
```bash
# Check all 10 Prometheus targets are UP
make prometheus-forward
open http://localhost:9090/targets

# Check Promtail is discovering pods
make promtail-logs
```

**Seed job failed**
```bash
# Check seed job logs
kubectl logs -n banking -l job-name=banking-seed

# Re-run seed manually (after services are healthy)
make seed
```

**Services not ready after install**
```bash
kubectl get pods -n banking    # all should be Running
kubectl get pods -n monitoring # all should be Running
```

**Out of disk space**
```bash
docker system prune -f
kubectl delete pvc --all -n monitoring   # wipes Prometheus/Loki/Grafana data
make monitoring-helm-install             # recreates PVCs fresh
```
