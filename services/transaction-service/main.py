import os
import sys
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy.orm import Session

from observability import create_app, get_logger
from database import get_db, init_db
from chaos import apply_chaos
from http_client import make_client
from models import Transaction

log = get_logger()
SERVICE = "transaction-service"

ACCOUNT_SERVICE_URL = os.getenv("ACCOUNT_SERVICE_URL", "http://account-service:8003")
LEDGER_SERVICE_URL = os.getenv("LEDGER_SERVICE_URL", "http://ledger-service:8005")
FRAUD_SERVICE_URL = os.getenv("FRAUD_SERVICE_URL", "http://fraud-service:8006")
NOTIFICATION_SERVICE_URL = os.getenv("NOTIFICATION_SERVICE_URL", "http://notification-service:8007")


@asynccontextmanager
async def lifespan(app):
    init_db()
    log.info("transaction-service started")
    yield

app = create_app("Transaction Service", lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class DepositRequest(BaseModel):
    account_id: str
    amount: float
    description: Optional[str] = "Deposit"


class WithdrawalRequest(BaseModel):
    account_id: str
    amount: float
    description: Optional[str] = "Withdrawal"


class TransferRequest(BaseModel):
    source_account_id: str
    destination_account_id: str
    amount: float
    description: Optional[str] = "Transfer"


class TransactionResponse(BaseModel):
    id: str
    transaction_type: str
    source_account_id: Optional[str]
    destination_account_id: Optional[str]
    amount: float
    currency: str
    status: str
    description: Optional[str]
    created_at: str


# ── Background tasks ───────────────────────────────────────────────────────────

async def _post_transaction_tasks(tx: dict, account_id: str, customer_id: Optional[str] = None):
    """Fire-and-forget: fraud analysis + notification."""
    async with make_client(FRAUD_SERVICE_URL) as client:
        try:
            await client.post("/fraud/analyze", json=tx)
        except Exception as e:
            log.warning("fraud service call failed", error=str(e))

    async with make_client(NOTIFICATION_SERVICE_URL) as client:
        try:
            await client.post("/notifications/send", json={
                "customer_id": customer_id,
                "notification_type": "transaction",
                "channel": "email",
                "message": f"Transaction {tx['id']}: {tx['transaction_type']} of ${tx['amount']:.2f}",
            })
        except Exception as e:
            log.warning("notification service call failed", error=str(e))


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/transactions/deposit", response_model=TransactionResponse, status_code=201)
async def deposit(req: DepositRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    err = await apply_chaos(SERVICE)
    if err:
        raise HTTPException(status_code=503, detail=err["detail"])

    if req.amount <= 0:
        raise HTTPException(status_code=422, detail="Amount must be positive")

    tx = Transaction(
        transaction_type="deposit",
        destination_account_id=req.account_id,
        amount=req.amount,
        description=req.description,
        status="pending",
    )
    db.add(tx)
    db.commit()

    # Update account balance
    async with make_client(ACCOUNT_SERVICE_URL) as client:
        resp = await client.patch(f"/accounts/{req.account_id}/balance", json={
            "amount": req.amount,
            "operation": "deposit",
        })
        if resp.status_code != 200:
            tx.status = "failed"
            db.commit()
            raise HTTPException(status_code=resp.status_code, detail=resp.json())

    # Record in ledger
    async with make_client(LEDGER_SERVICE_URL) as client:
        try:
            await client.post("/ledger/entries", json={
                "transaction_id": tx.id,
                "account_id": req.account_id,
                "entry_type": "credit",
                "amount": req.amount,
                "description": req.description,
            })
        except Exception as e:
            log.warning("ledger entry failed", error=str(e))

    tx.status = "completed"
    db.commit()
    db.refresh(tx)

    tx_dict = _to_dict(tx)
    background_tasks.add_task(_post_transaction_tasks, tx_dict, req.account_id)
    log.info("deposit completed", transaction_id=tx.id, amount=req.amount, account_id=req.account_id)
    return tx_dict


@app.post("/transactions/withdraw", response_model=TransactionResponse, status_code=201)
async def withdraw(req: WithdrawalRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    err = await apply_chaos(SERVICE)
    if err:
        raise HTTPException(status_code=503, detail=err["detail"])

    if req.amount <= 0:
        raise HTTPException(status_code=422, detail="Amount must be positive")

    tx = Transaction(
        transaction_type="withdrawal",
        source_account_id=req.account_id,
        amount=req.amount,
        description=req.description,
        status="pending",
    )
    db.add(tx)
    db.commit()

    async with make_client(ACCOUNT_SERVICE_URL) as client:
        resp = await client.patch(f"/accounts/{req.account_id}/balance", json={
            "amount": -req.amount,
            "operation": "withdrawal",
        })
        if resp.status_code != 200:
            tx.status = "failed"
            db.commit()
            raise HTTPException(status_code=resp.status_code, detail=resp.json())

    async with make_client(LEDGER_SERVICE_URL) as client:
        try:
            await client.post("/ledger/entries", json={
                "transaction_id": tx.id,
                "account_id": req.account_id,
                "entry_type": "debit",
                "amount": req.amount,
                "description": req.description,
            })
        except Exception as e:
            log.warning("ledger entry failed", error=str(e))

    tx.status = "completed"
    db.commit()
    db.refresh(tx)

    tx_dict = _to_dict(tx)
    background_tasks.add_task(_post_transaction_tasks, tx_dict, req.account_id)
    log.info("withdrawal completed", transaction_id=tx.id, amount=req.amount, account_id=req.account_id)
    return tx_dict


@app.post("/transactions/transfer", response_model=TransactionResponse, status_code=201)
async def transfer(req: TransferRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    err = await apply_chaos(SERVICE)
    if err:
        raise HTTPException(status_code=503, detail=err["detail"])

    if req.amount <= 0:
        raise HTTPException(status_code=422, detail="Amount must be positive")
    if req.source_account_id == req.destination_account_id:
        raise HTTPException(status_code=422, detail="Source and destination must differ")

    tx = Transaction(
        transaction_type="transfer",
        source_account_id=req.source_account_id,
        destination_account_id=req.destination_account_id,
        amount=req.amount,
        description=req.description,
        status="pending",
    )
    db.add(tx)
    db.commit()

    async with make_client(ACCOUNT_SERVICE_URL) as client:
        # Debit source
        resp = await client.patch(f"/accounts/{req.source_account_id}/balance", json={
            "amount": -req.amount, "operation": "transfer_out",
        })
        if resp.status_code != 200:
            tx.status = "failed"
            db.commit()
            raise HTTPException(status_code=resp.status_code, detail=resp.json())

        # Credit destination
        resp = await client.patch(f"/accounts/{req.destination_account_id}/balance", json={
            "amount": req.amount, "operation": "transfer_in",
        })
        if resp.status_code != 200:
            # Attempt rollback
            await client.patch(f"/accounts/{req.source_account_id}/balance", json={
                "amount": req.amount, "operation": "transfer_rollback",
            })
            tx.status = "failed"
            db.commit()
            raise HTTPException(status_code=resp.status_code, detail=resp.json())

    async with make_client(LEDGER_SERVICE_URL) as client:
        try:
            await client.post("/ledger/entries", json={
                "transaction_id": tx.id,
                "account_id": req.source_account_id,
                "entry_type": "debit",
                "amount": req.amount,
                "description": req.description,
            })
            await client.post("/ledger/entries", json={
                "transaction_id": tx.id,
                "account_id": req.destination_account_id,
                "entry_type": "credit",
                "amount": req.amount,
                "description": req.description,
            })
        except Exception as e:
            log.warning("ledger entries failed", error=str(e))

    tx.status = "completed"
    db.commit()
    db.refresh(tx)

    tx_dict = _to_dict(tx)
    background_tasks.add_task(_post_transaction_tasks, tx_dict, req.source_account_id)
    log.info("transfer completed", transaction_id=tx.id, amount=req.amount,
             from_account=req.source_account_id, to_account=req.destination_account_id)
    return tx_dict


@app.get("/transactions/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(transaction_id: str, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return _to_dict(tx)


@app.get("/transactions/account/{account_id}", response_model=list[TransactionResponse])
async def list_transactions(account_id: str, limit: int = 50, db: Session = Depends(get_db)):
    txs = db.query(Transaction).filter(
        (Transaction.source_account_id == account_id) |
        (Transaction.destination_account_id == account_id)
    ).order_by(Transaction.created_at.desc()).limit(limit).all()
    return [_to_dict(tx) for tx in txs]


# ── Chaos config endpoint ──────────────────────────────────────────────────────

@app.post("/chaos/config")
async def set_chaos_config(latency_ms: int = 0, error_rate: float = 0.0):
    from chaos import set_chaos
    set_chaos(SERVICE, latency_ms=latency_ms, error_rate=error_rate)
    log.warning("chaos config updated", service=SERVICE, latency_ms=latency_ms, error_rate=error_rate)
    return {"service": SERVICE, "latency_ms": latency_ms, "error_rate": error_rate}


@app.delete("/chaos/config")
async def clear_chaos_config():
    from chaos import clear_chaos
    clear_chaos(SERVICE)
    return {"service": SERVICE, "chaos": "cleared"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _to_dict(tx: Transaction) -> dict:
    return {
        "id": tx.id,
        "transaction_type": tx.transaction_type,
        "source_account_id": tx.source_account_id,
        "destination_account_id": tx.destination_account_id,
        "amount": tx.amount,
        "currency": tx.currency,
        "status": tx.status,
        "description": tx.description,
        "created_at": tx.created_at.isoformat(),
    }
