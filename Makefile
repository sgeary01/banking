REGISTRY ?= banking
TAG      ?= latest

SERVICES = api-gateway auth-service customer-service account-service \
           transaction-service ledger-service fraud-service \
           notification-service reporting-service chaos-service

.PHONY: build-base build build-service \
        up down \
        monitoring-up monitoring-down \
        seed helm-install helm-uninstall \
        logs clean grafana network

# ── Network ─────────────────────────────────────────────────────
## Create the shared external network (idempotent)
network:
	docker network create banking 2>/dev/null || true

# ── Images ──────────────────────────────────────────────────────
## Build base image first (all services depend on this)
build-base:
	docker build -t $(REGISTRY)/base:$(TAG) ./base

## Build all service images — context is repo root so shared/ is reachable
build: build-base
	@for svc in $(SERVICES); do \
		echo "==> Building $$svc"; \
		docker build \
			--build-arg BASE_IMAGE=$(REGISTRY)/base:$(TAG) \
			-f ./services/$$svc/Dockerfile \
			-t $(REGISTRY)/$$svc:$(TAG) \
			.; \
	done
	@echo "==> Building frontend"
	docker build -t $(REGISTRY)/frontend:$(TAG) ./frontend

## Build a single service: make build-service SVC=account-service
build-service: build-base
	docker build \
		--build-arg BASE_IMAGE=$(REGISTRY)/base:$(TAG) \
		-f ./services/$(SVC)/Dockerfile \
		-t $(REGISTRY)/$(SVC):$(TAG) \
		.

# ── Banking app ─────────────────────────────────────────────────
## Start the banking app (creates shared network first)
up: network
	docker-compose up -d

## Stop the banking app (leaves volumes intact, leaves network up)
down:
	docker-compose down

## Stop the banking app AND wipe all data volumes
down-clean:
	docker-compose down -v

# ── Monitoring stack ────────────────────────────────────────────
## Start monitoring (Prometheus + Loki + Promtail + Grafana)
## Banking app must be running first so the shared network exists.
monitoring-up: network
	docker-compose -f docker-compose.monitoring.yml up -d

## Stop monitoring only (banking app keeps running)
monitoring-down:
	docker-compose -f docker-compose.monitoring.yml down

## Stop monitoring AND wipe its data volumes (Prometheus/Loki/Grafana state)
monitoring-clean:
	docker-compose -f docker-compose.monitoring.yml down -v

## Open Grafana in the browser
grafana:
	open http://localhost:3001

# ── Seed data ───────────────────────────────────────────────────
## Populate services with test customers, accounts, and transactions
seed:
	docker-compose --profile seed run --rm seed

# ── Kubernetes ──────────────────────────────────────────────────
## Deploy to local K8s via Helm
helm-install: build
	helm upgrade --install banking ./helm/banking \
		--namespace banking --create-namespace \
		--values ./helm/banking/values.yaml

## Uninstall from K8s
helm-uninstall:
	helm uninstall banking --namespace banking

# ── Ops ─────────────────────────────────────────────────────────
## Tail logs — all services, or one: make logs SVC=auth-service
logs:
ifdef SVC
	docker-compose logs -f $(SVC)
else
	docker-compose logs -f
endif

## Remove all built images
clean:
	@for svc in $(SERVICES) frontend base; do \
		docker rmi $(REGISTRY)/$$svc:$(TAG) 2>/dev/null || true; \
	done
