# Banking Demo — O11y & Kubernetes Learning Lab

A realistic multi-service banking application built for learning **observability**, **Kubernetes**, and **incident management** with [Resolve](https://resolve.io). Runs entirely on a laptop.

---

## What's Inside

10 Python microservices, a React frontend, a chaos engineering service, and a full observability stack — all wired together and ready to generate real signals.

### Services

| Service | Port | Responsibility |
|---|---|---|
| `api-gateway` | 8000 | Single entry point — routes all external traffic |
| `auth-service` | 8001 | JWT authentication, user registration & login |
| `customer-service` | 8002 | Customer profiles & KYC data |
| `account-service` | 8003 | Bank accounts, balances |
| `transaction-service` | 8004 | Deposits, withdrawals, transfers — the core flow |
| `ledger-service` | 8005 | Double-entry accounting records |
| `fraud-service` | 8006 | Real-time fraud scoring on every transaction |
| `notification-service` | 8007 | Transaction alerts & notifications |
| `reporting-service` | 8008 | Aggregated balance and transaction reports |
| `chaos-service` | 8009 | Inject latency and errors into any service |
| `frontend` | 3000 | React UI — accounts, transactions, chaos panel |

### Observability Stack (separate compose)

| Tool | Port | Purpose |
|---|---|---|
| Grafana | 3001 | Dashboards — pre-provisioned Banking Overview |
| Prometheus | 9090 | Metrics scraping from all 10 services |
| Loki | 3100 | Log aggregation |
| Promtail | — | Ships Docker container logs to Loki |

---

## Architecture

```
Browser
  └── frontend :3000
        └── api-gateway :8000
              ├── auth-service :8001
              ├── customer-service :8002
              ├── account-service :8003
              ├── transaction-service :8004  ──► ledger-service :8005
              │                               ──► fraud-service :8006
              │                               ──► notification-service :8007
              ├── reporting-service :8008
              └── chaos-service :8009

Monitoring (isolated network)
  Prometheus ──► scrapes /metrics on all services
  Promtail   ──► reads Docker container logs ──► Loki
  Grafana    ──► queries Prometheus + Loki
```

**Two Docker networks keep monitoring signals clean:**
- `banking` — app services + Prometheus (for scraping)
- `monitoring` — Prometheus + Loki + Promtail + Grafana (internal only)

Grafana never appears as a peer on the banking network, so its own metrics and logs don't pollute your dashboards.

---

## Prerequisites

| Tool | Install |
|---|---|
| Docker + Docker Compose | [OrbStack](https://orbstack.dev) (recommended for Mac) or Docker Desktop |
| `make` | Included on macOS |
| `helm` | `brew install helm` (only needed for K8s deploy) |

> **Resource budget:** the full stack (app + monitoring) uses ~3 GB RAM and ~4 CPU cores under load. Tested on a MacBook with 24 GB RAM.

---

## Quick Start

```bash
# 1. Build all images (takes ~3 min on first run, fast after that)
make build

# 2. Start the banking app
make up

# 3. Start the monitoring stack
make monitoring-up

# 4. Seed realistic test data (customers, accounts, transactions)
make seed
```

Then open:

| URL | What you'll see |
|---|---|
| http://localhost:3000 | React frontend — login with `alice@example.com` / `password123` |
| http://localhost:3001 | Grafana — `admin` / `admin` |
| http://localhost:9090 | Prometheus — explore raw metrics |

---

## Day-to-Day Commands

```bash
# App lifecycle
make up               # start banking services
make down             # stop (volumes kept)
make down-clean       # stop + wipe all data volumes

# Monitoring lifecycle
make monitoring-up    # start Grafana / Prometheus / Loki / Promtail
make monitoring-down  # stop monitoring (app keeps running)
make monitoring-clean # stop monitoring + wipe Prometheus/Loki/Grafana volumes

# Building
make build            # rebuild all images
make build-service SVC=transaction-service  # rebuild one service

# Seed data
make seed             # populate test customers, accounts, transactions

# Logs
make logs             # tail all service logs
make logs SVC=fraud-service  # tail one service

# Open Grafana
make grafana

# Cleanup
make clean            # remove all built images
```

---

## Generating Signals with Chaos

The chaos service lets you inject faults from the Grafana dashboard, the frontend Chaos Panel, or the API directly.

### Pre-built Scenarios

```bash
# Payment outage — transaction-service returns 50% errors, auto-generates traffic
curl -X POST http://localhost:8009/chaos/scenarios/payment_outage/trigger

# Slow accounts — 3 second latency on all account lookups
curl -X POST http://localhost:8009/chaos/scenarios/high_latency/trigger

# Cascade failure — transaction + account both degraded
curl -X POST http://localhost:8009/chaos/scenarios/cascade_failure/trigger

# Fraud spike — high-value transactions to trigger fraud alerts
curl -X POST http://localhost:8009/chaos/scenarios/fraud_spike/trigger

# Notification flood — burst of small transactions
curl -X POST http://localhost:8009/chaos/scenarios/notification_flood/trigger

# Clear everything
curl -X POST http://localhost:8009/chaos/scenarios/clear
```

### Manual Injection

```bash
# 30% error rate on the ledger service
curl -X POST http://localhost:8009/chaos/inject \
  -H 'Content-Type: application/json' \
  -d '{"service": "ledger-service", "error_rate": 0.3}'

# 2 second latency on fraud checks
curl -X POST http://localhost:8009/chaos/inject \
  -H 'Content-Type: application/json' \
  -d '{"service": "fraud-service", "latency_ms": 2000}'
```

> Scenarios auto-discover seeded accounts and generate a burst of real transactions so errors appear in Grafana immediately — no manual traffic generation needed.

---

## Observability Details

### Metrics

Every service exposes `/metrics` in Prometheus format via `prometheus-fastapi-instrumentator`. Key metrics:

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

Promtail ships these from Docker to Loki. Every log line carries `request_id` and `trace_id` so you can correlate logs across services for a single request.

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

OpenTelemetry SDK is wired into every service (FastAPI + HTTPX instrumented). Traces are collected but silently dropped until you point `OTEL_EXPORTER_OTLP_ENDPOINT` at a collector (Tempo, Jaeger, etc.):

```yaml
# In docker-compose.yml, add to any service:
environment:
  OTEL_EXPORTER_OTLP_ENDPOINT: http://tempo:4318
```

---

## Grafana Dashboard

The **Banking Services Overview** dashboard is pre-provisioned — no import needed.

| Panel | What it shows |
|---|---|
| Total Requests | Aggregate request count over the last 5 min |
| Error Rate % | Global 5xx rate — 0% when healthy, spikes under chaos |
| Services Up | Count of healthy services (should be 10) |
| Requests/sec per Service | Per-service throughput time series |
| Error Rate per Service | Per-service 5xx rate — isolates the broken service |
| P95 Latency per Service | Tail latency time series — shows latency injection clearly |
| Banking Service Logs | Live log stream from all services |

Datasource UIDs are pinned (`banking-prometheus`, `banking-loki`) so dashboards survive Grafana restarts without breaking.

---

## Project Layout

```
banking/
├── Makefile                        # all common tasks
├── docker-compose.yml              # banking app stack
├── docker-compose.monitoring.yml   # observability stack (separate)
│
├── base/                           # shared Python base image
│   ├── Dockerfile
│   └── requirements.txt            # all shared deps (FastAPI, structlog, OTEL, ...)
│
├── shared/                         # library mounted into every service
│   ├── observability.py            # logging + tracing + Prometheus wiring
│   ├── database.py                 # SQLAlchemy setup
│   ├── chaos.py                    # in-process chaos state store
│   └── http_client.py              # instrumented HTTPX client
│
├── services/
│   ├── api-gateway/
│   ├── auth-service/
│   ├── account-service/
│   ├── transaction-service/
│   └── ...                         # one directory per service
│
├── frontend/                       # React app
├── seed/                           # seed.py — populates test data
├── helm/banking/                   # Helm chart for Kubernetes deploy
│
└── monitoring/
    ├── prometheus/prometheus.yml
    ├── loki/loki-config.yml
    ├── promtail/promtail-config.yml
    └── grafana/provisioning/
        ├── datasources/datasources.yml
        └── dashboards/banking-overview.json
```

---

## Kubernetes (Helm)

```bash
# Build images first (they need to be accessible to your cluster)
make build

# Deploy to local cluster (k3d, kind, Docker Desktop K8s)
make helm-install

# Uninstall
make helm-uninstall
```

The Helm chart deploys all 10 services + frontend with resource requests tuned for a laptop cluster (50m CPU / 96Mi RAM per service). Override in `helm/banking/values.yaml`.

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
3. In the `Dockerfile`, copy shared libs:
   ```dockerfile
   ARG BASE_IMAGE=banking/base:latest
   FROM ${BASE_IMAGE}
   COPY shared/ /app/shared/
   COPY services/my-service/ .
   ```
4. Add to `docker-compose.yml` and `monitoring/prometheus/prometheus.yml`
5. Add to `SERVICES` in `Makefile`

You get `/health`, `/ready`, `/metrics`, structured logging, and tracing for free.

---

## Connecting to Resolve

Once the stack is running:

1. Point Resolve's Prometheus integration at `http://<your-machine-ip>:9090`
2. Point Resolve's Loki integration at `http://<your-machine-ip>:3100`
3. Trigger a chaos scenario and watch Resolve surface the incident from the metrics spike

The `payment_outage` scenario is the most dramatic — it takes transaction-service to ~50% error rate within seconds, which should generate clear signal for alert evaluation.

---

## Troubleshooting

**`make up` fails — network not found**
```bash
make network   # creates the 'banking' Docker network
make up
```

**Grafana shows "No data"**
- Check Prometheus targets: http://localhost:9090/targets — all should be `UP`
- Verify the monitoring stack is running: `docker ps | grep banking`
- Trigger chaos to generate errors: `curl -X POST http://localhost:8009/chaos/scenarios/payment_outage/trigger`

**Seed fails**
- Services must be fully started before seeding: `docker-compose ps` — all should be `Up`
- If data looks corrupt: `make down-clean && make up && make seed`

**Images not found after rebuild**
```bash
make clean     # remove old images
make build     # rebuild from scratch
make up
```

**Out of disk space**
```bash
docker system prune -f          # remove stopped containers and dangling images
make monitoring-clean           # wipe monitoring volumes (Prometheus/Loki data)
```
