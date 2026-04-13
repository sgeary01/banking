import asyncio
import os
import random
import sys
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from observability import create_app, get_logger
from http_client import make_client

log = get_logger()

TRANSACTION_SERVICE_URL = os.getenv("TRANSACTION_SERVICE_URL", "http://transaction-service:8004")
ACCOUNT_SERVICE_URL = os.getenv("ACCOUNT_SERVICE_URL", "http://account-service:8003")
FRAUD_SERVICE_URL = os.getenv("FRAUD_SERVICE_URL", "http://fraud-service:8006")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8007")

# Map service name → its internal URL for chaos config endpoints
SERVICE_URLS = {
    "transaction-service": TRANSACTION_SERVICE_URL,
    "account-service": ACCOUNT_SERVICE_URL,
    "fraud-service": FRAUD_SERVICE_URL,
    "notification-service": NOTIFICATION_SERVICE_URL,
}

# Pre-defined chaos scenarios
SCENARIOS = {
    "payment_outage": {
        "description": "Transaction service returning 50% errors — payments failing",
        "services": {"transaction-service": {"latency_ms": 0, "error_rate": 0.5}},
        "generator": "transaction_load",
        "load_count": 60,
        "load_high_value": False,
    },
    "high_latency": {
        "description": "Account service slow — 3 second delays on all account operations",
        "services": {"account-service": {"latency_ms": 3000, "error_rate": 0.0}},
        "generator": "transaction_load",
        "load_count": 30,
        "load_high_value": False,
    },
    "fraud_spike": {
        "description": "Generates a burst of high-value transactions to trigger fraud alerts",
        "services": {},
        "generator": "fraud_spike",
        "load_count": 20,
        "load_high_value": True,
    },
    "cascade_failure": {
        "description": "Transaction + account services both degraded — tests circuit breaking",
        "services": {
            "transaction-service": {"latency_ms": 2000, "error_rate": 0.3},
            "account-service": {"latency_ms": 1000, "error_rate": 0.2},
        },
        "generator": "transaction_load",
        "load_count": 60,
        "load_high_value": False,
    },
    "notification_flood": {
        "description": "Generates many small transactions to flood the notification service",
        "services": {},
        "generator": "notification_flood",
        "load_count": 40,
        "load_high_value": False,
    },
}


@asynccontextmanager
async def lifespan(app):
    log.info("chaos-service started")
    yield

app = create_app("Chaos Service", lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class ChaosConfig(BaseModel):
    service: str
    latency_ms: int = 0
    error_rate: float = 0.0


class ScenarioTrigger(BaseModel):
    account_ids: Optional[list[str]] = None  # needed for load generators


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/chaos/scenarios")
async def list_scenarios():
    return [
        {"name": name, "description": s["description"]}
        for name, s in SCENARIOS.items()
    ]


@app.post("/chaos/scenarios/{scenario_name}/trigger")
async def trigger_scenario(scenario_name: str, body: ScenarioTrigger = ScenarioTrigger()):
    if scenario_name not in SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_name}")

    scenario = SCENARIOS[scenario_name]
    log.warning("chaos scenario triggered", scenario=scenario_name)

    # Push chaos config to each affected service
    for svc_name, config in scenario.get("services", {}).items():
        url = SERVICE_URLS.get(svc_name)
        if not url:
            continue
        async with make_client(url) as client:
            try:
                await client.post("/chaos/config", params=config)
                log.info("chaos config pushed", service=svc_name, config=config)
            except Exception as e:
                log.warning("failed to push chaos config", service=svc_name, error=str(e))

    # Run load generators — auto-discover accounts if none provided
    generator = scenario.get("generator")
    count = scenario.get("load_count", 30)
    high_value = scenario.get("load_high_value", False)

    account_ids = body.account_ids or []
    if generator and not account_ids:
        # Auto-discover active accounts from account-service
        try:
            async with make_client(ACCOUNT_SERVICE_URL) as client:
                resp = await client.get("/accounts", params={"limit": 50})
                if resp.status_code == 200:
                    accounts = resp.json()
                    account_ids = [a["id"] for a in accounts if a.get("account_type") != "credit"]
                    log.info("auto-discovered accounts for load generation", count=len(account_ids))
        except Exception as e:
            log.warning("failed to discover accounts", error=str(e))

    if generator and account_ids:
        if generator in ("transaction_load", "fraud_spike"):
            asyncio.create_task(_generate_transactions(account_ids, count=count, high_value=high_value))
        elif generator == "notification_flood":
            asyncio.create_task(_notification_flood(account_ids))
    elif generator and not account_ids:
        log.warning("no accounts found for load generation — Grafana will show no traffic until you run: make seed")

    return {
        "scenario": scenario_name,
        "description": scenario["description"],
        "status": "triggered",
        "load_generating": bool(generator and account_ids),
        "accounts_used": len(account_ids),
    }


@app.post("/chaos/scenarios/clear")
async def clear_all_chaos():
    """Remove chaos config from all services."""
    log.info("clearing all chaos")
    for svc_name, url in SERVICE_URLS.items():
        async with make_client(url) as client:
            try:
                await client.delete("/chaos/config")
            except Exception as e:
                log.warning("failed to clear chaos config", service=svc_name, error=str(e))
    return {"status": "cleared"}


@app.post("/chaos/inject")
async def inject_chaos(config: ChaosConfig):
    """Manually inject chaos into a specific service."""
    url = SERVICE_URLS.get(config.service)
    if not url:
        raise HTTPException(status_code=404, detail=f"Unknown service: {config.service}")

    async with make_client(url) as client:
        resp = await client.post("/chaos/config", params={
            "latency_ms": config.latency_ms,
            "error_rate": config.error_rate,
        })
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Failed to inject chaos")

    log.warning("chaos injected", service=config.service,
                latency_ms=config.latency_ms, error_rate=config.error_rate)
    return {"service": config.service, "latency_ms": config.latency_ms, "error_rate": config.error_rate}


@app.post("/chaos/load/transactions")
async def generate_transaction_load(account_ids: list[str], count: int = 20, high_value: bool = False):
    """Generate a burst of transactions — drives metrics and potentially fraud alerts."""
    asyncio.create_task(_generate_transactions(account_ids, count, high_value))
    return {"status": "started", "count": count, "high_value": high_value}


# ── Load generators ────────────────────────────────────────────────────────────

async def _generate_transactions(account_ids: list[str], count: int, high_value: bool):
    log.info("starting transaction load generation", count=count)
    async with make_client(TRANSACTION_SERVICE_URL) as client:
        for i in range(count):
            account_id = random.choice(account_ids)
            amount = random.uniform(5000, 15000) if high_value else random.uniform(10, 500)
            try:
                await client.post("/transactions/deposit", json={
                    "account_id": account_id,
                    "amount": round(amount, 2),
                    "description": f"Chaos load transaction {i+1}",
                })
            except Exception as e:
                log.warning("load transaction failed", error=str(e))
            await asyncio.sleep(0.1)
    log.info("transaction load generation complete", count=count)


async def _fraud_spike(account_ids: list[str]):
    """Generate high-value transactions to trigger fraud detection."""
    await _generate_transactions(account_ids, count=10, high_value=True)


async def _notification_flood(account_ids: list[str]):
    """Generate many small transactions to flood notifications."""
    await _generate_transactions(account_ids, count=30, high_value=False)
