import os
import sys
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import HTTPException
from pydantic import BaseModel

from observability import create_app, get_logger
from http_client import make_client

log = get_logger()

ACCOUNT_SERVICE_URL = os.getenv("ACCOUNT_SERVICE_URL", "http://account-service:8003")
LEDGER_SERVICE_URL = os.getenv("LEDGER_SERVICE_URL", "http://ledger-service:8005")
TRANSACTION_SERVICE_URL = os.getenv("TRANSACTION_SERVICE_URL", "http://transaction-service:8004")
CUSTOMER_SERVICE_URL = os.getenv("CUSTOMER_SERVICE_URL", "http://customer-service:8002")


@asynccontextmanager
async def lifespan(app):
    log.info("reporting-service started")
    yield

app = create_app("Reporting Service", lifespan=lifespan)


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/reports/account/{account_id}/statement")
async def account_statement(account_id: str, limit: int = 50):
    """Full statement: account info + ledger entries."""
    async with make_client(ACCOUNT_SERVICE_URL) as client:
        resp = await client.get(f"/accounts/{account_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Account not found")
        account = resp.json()

    async with make_client(LEDGER_SERVICE_URL) as client:
        resp = await client.get(f"/ledger/account/{account_id}", params={"limit": limit})
        entries = resp.json() if resp.status_code == 200 else []

    log.info("statement generated", account_id=account_id, entries=len(entries))
    return {
        "account": account,
        "entries": entries,
        "entry_count": len(entries),
    }


@app.get("/reports/account/{account_id}/summary")
async def account_summary(account_id: str):
    """Balance summary with credit/debit totals from ledger."""
    async with make_client(ACCOUNT_SERVICE_URL) as client:
        resp = await client.get(f"/accounts/{account_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Account not found")
        account = resp.json()

    async with make_client(LEDGER_SERVICE_URL) as client:
        resp = await client.get(f"/ledger/account/{account_id}", params={"limit": 1000})
        entries = resp.json() if resp.status_code == 200 else []

    total_credits = sum(e["amount"] for e in entries if e["entry_type"] == "credit")
    total_debits = sum(e["amount"] for e in entries if e["entry_type"] == "debit")

    return {
        "account_id": account_id,
        "account_number": account["account_number"],
        "current_balance": account["balance"],
        "total_credits": round(total_credits, 2),
        "total_debits": round(total_debits, 2),
        "transaction_count": len(entries),
    }


@app.get("/reports/customer/{customer_id}/overview")
async def customer_overview(customer_id: str):
    """Full customer overview: profile + all accounts + recent transactions."""
    async with make_client(CUSTOMER_SERVICE_URL) as client:
        resp = await client.get(f"/customers/{customer_id}")
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="Customer not found")
        customer = resp.json()

    async with make_client(ACCOUNT_SERVICE_URL) as client:
        resp = await client.get(f"/accounts/customer/{customer_id}")
        accounts = resp.json() if resp.status_code == 200 else []

    total_balance = sum(a["balance"] for a in accounts)

    recent_transactions = []
    for account in accounts[:3]:  # limit to first 3 accounts to avoid too many calls
        async with make_client(TRANSACTION_SERVICE_URL) as client:
            resp = await client.get(f"/transactions/account/{account['id']}", params={"limit": 10})
            if resp.status_code == 200:
                recent_transactions.extend(resp.json())

    recent_transactions.sort(key=lambda t: t["created_at"], reverse=True)

    log.info("customer overview generated", customer_id=customer_id, account_count=len(accounts))
    return {
        "customer": customer,
        "accounts": accounts,
        "total_balance": round(total_balance, 2),
        "recent_transactions": recent_transactions[:20],
    }


@app.get("/reports/system/summary")
async def system_summary():
    """High-level system stats — useful for the dashboard."""
    stats = {}

    async with make_client(CUSTOMER_SERVICE_URL) as client:
        resp = await client.get("/customers", params={"limit": 1000})
        stats["total_customers"] = len(resp.json()) if resp.status_code == 200 else 0

    log.info("system summary generated")
    return stats
