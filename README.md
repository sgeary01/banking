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
| Grafana | Dashboards — pre-provisioned Banking Overview |
| Prometheus | Metrics scraping from all services |
| Loki | Log aggregation |
| Promtail | Ships pod logs to Loki (DaemonSet, static file discovery) |

### Resolve Satellite

The Resolve satellite runs in-cluster and connects to `dev0.resolve.ai`. It observes service topology via CoreDNS dnstap, giving Resolve visibility into how services connect.

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
  ├── namespace: monitoring  ← Prometheus, Loki, Promtail, Grafana
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

**Default login:** `alice@example.com` / `password123` (and 9 other seeded users)

---

## Prerequisites

| Tool | Install |
|---|---|
| [Docker Desktop](https://www.docker.com/products/docker-desktop/) | Container runtime |
| `k3d` | `brew install k3d` |
| `helm` | `brew install helm` |
| `kubectl` | `brew install kubectl` |
| `make` | Included on macOS |

> **Resource budget:** allocate at least 8 GB RAM to Docker Desktop. The full stack uses ~4–5 GB under normal load, more under chaos. The Resolve satellite alone requires ~2 GB.

---

## Quick Start

```bash
# One command — creates cluster, builds images, deploys everything
make k3d-up
```

That's it. The bootstrap script:
1. Creates the k3d cluster with the correct NodePort mappings
2. Builds all Docker images
3. Imports images into the cluster (no registry needed)
4. Helm-installs the banking app and monitoring stack

**Seed data is automatic.** A `banking-seeder` deployment waits for all services to be healthy and seeds 10 customers, their accounts, and transaction history on every startup. No manual seed step required.

**Resolve satellite** must be set up separately — see [Resolve Setup](#resolve-setup) below.

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

## Secrets Management

Secrets are **never committed to git**. They are created manually as Kubernetes secrets and referenced by name in Helm values.

```bash
# Resolve satellite ingest token
kubectl create secret generic resolve-ingest-token \
  --from-literal=token=<YOUR_TOKEN> \
  -n default

# Future secrets follow the same pattern:
# kubectl create secret generic <name> --from-literal=<key>=<value> -n <namespace>
```

Values files reference secrets by name only:
```yaml
# helm/banking/resolve-values.yaml
ingest:
  tokenSecretName: resolve-ingest-token
  host: receiver.dev0.resolve.ai
```

---

## Resolve Setup

The Resolve satellite runs in the `default` namespace and connects to `dev0.resolve.ai`.

### 1. Create the ingest token secret

```bash
kubectl create secret generic resolve-ingest-token \
  --from-literal=token=<YOUR_TOKEN> \
  -n default
```

### 2. Install the satellite

```bash
helm upgrade --install resolve-satellite \
  oci://ghcr.io/resolve-ai/charts/satellite-chart \
  --namespace default \
  -f helm/banking/resolve-values.yaml
```

### 3. Verify

```bash
kubectl get pods -n default | grep satellite
kubectl logs -n default resolve-satellite-satellite-chart-0 | grep -i connected
```

The satellite uses CoreDNS dnstap for service topology — configured automatically during bootstrap. Once connected, services and their DNS-based connections appear in the Resolve UI.

---

## Generating Signals with Chaos

Use the frontend Chaos Panel at http://localhost:30080 or call the API directly.

### Pre-built Scenarios

```bash
# Payment outage — transaction-service returns ~50% errors
curl -X POST http://localhost:30000/chaos/scenarios/payment_outage/trigger

# High latency — 3 second delay on account lookups
curl -X POST http://localhost:30000/chaos/scenarios/high_latency/trigger

# Cascade failure — transaction + account both degraded simultaneously
curl -X POST http://localhost:30000/chaos/scenarios/cascade_failure/trigger

# Fraud spike — large transactions to trigger fraud alerts
curl -X POST http://localhost:30000/chaos/scenarios/fraud_spike/trigger

# Notification flood — burst of small transactions
curl -X POST http://localhost:30000/chaos/scenarios/notification_flood/trigger

# Clear everything
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

> `payment_outage` is the most dramatic starting point — hits ~50% error rate within seconds, generating clear signal in Grafana and Resolve.

---

## Observability Details

### Metrics

Every service exposes `/metrics` in Prometheus format. Key queries:

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
```

> The status label is `status="2xx"` / `status="5xx"` — not `status_code`.

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

Promtail ships pod logs to Loki using static file discovery (`/var/log/pods/banking_*/*/*.log`). Every log line carries `request_id` and `trace_id` for cross-service correlation.

Useful LogQL queries:

```logql
# All errors across services
{service=~".+"} | json | level="error"

# Fraud alerts
{service="fraud-service"} | json | event="fraud alert"

# Follow a single request across all services
{service=~".+"} | json | request_id="<id>"
```

### Grafana Dashboard

**Banking Services Overview** is pre-provisioned — open http://localhost:30030.

| Panel | What it shows |
|---|---|
| Total Requests | Aggregate request count |
| Error Rate % | Global 5xx rate — spikes under chaos |
| Services Up | Count of healthy services (should be 10) |
| Requests/sec per Service | Per-service throughput |
| Error Rate per Service | Isolates the broken service |
| P95 Latency per Service | Shows latency injection clearly |
| Banking Service Logs | Live log stream from all services |

### Tracing

OpenTelemetry is wired into every service. Traces are silently dropped until you point `OTEL_EXPORTER_OTLP_ENDPOINT` at a collector:

```yaml
# helm/banking/values.yaml
otelEndpoint: "http://tempo.monitoring.svc.cluster.local:4318"
```

---

## Project Layout

```
banking/
├── Makefile
├── scripts/
│   └── bootstrap-k3d.sh          # one-command cluster + deploy
│
├── base/                          # shared Python base image
│   ├── Dockerfile
│   └── requirements.txt
│
├── shared/                        # library copied into every service
│   ├── observability.py           # logging + tracing + Prometheus
│   ├── database.py
│   ├── chaos.py
│   └── http_client.py
│
├── services/
│   ├── api-gateway/
│   ├── auth-service/
│   └── ...                        # one directory per service
│
├── frontend/                      # React app + nginx config
│   └── nginx.conf                 # proxies /api/* → api-gateway in-cluster
│
├── seed/
│   └── seed.py                    # populates test data (runs automatically)
│
└── helm/
    ├── banking/                   # Helm chart — 10 services + frontend + seeder
    │   ├── values.yaml
    │   ├── resolve-values.yaml    # Resolve satellite config (no secrets)
    │   └── templates/
    │       ├── seed-job.yaml      # seeder Deployment — auto-seeds on every start
    │       └── ...
    └── monitoring/                # Helm chart — Prometheus, Loki, Promtail, Grafana
        ├── values.yaml
        ├── dashboards/banking-overview.json
        └── templates/
            ├── prometheus/        # Recreate strategy to avoid PVC lock conflicts
            ├── loki/
            ├── promtail/
            └── grafana/
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

**Out of disk space**
```bash
docker system prune -f
```
