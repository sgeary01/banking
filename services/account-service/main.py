import random
import sys
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from observability import create_app, get_logger
from database import get_db, init_db
from chaos import apply_chaos
from models import Account

log = get_logger()
SERVICE = "account-service"


@asynccontextmanager
async def lifespan(app):
    init_db()
    log.info("account-service started")
    yield

app = create_app("Account Service", lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class AccountCreate(BaseModel):
    customer_id: str
    account_type: str = "checking"  # checking | savings | credit
    initial_balance: float = 0.0


class BalanceUpdate(BaseModel):
    amount: float        # positive = credit, negative = debit
    operation: str       # deposit | withdrawal | transfer_in | transfer_out


class AccountResponse(BaseModel):
    id: str
    customer_id: str
    account_number: str
    account_type: str
    balance: float
    status: str
    created_at: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.get("/accounts", response_model=list[AccountResponse])
async def list_accounts(limit: int = 200, db: Session = Depends(get_db)):
    """Internal endpoint — used by chaos-service for load generation."""
    accounts = db.query(Account).filter(Account.status == "active").limit(limit).all()
    return [_to_response(a) for a in accounts]


@app.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_account(req: AccountCreate, db: Session = Depends(get_db)):
    err = await apply_chaos(SERVICE)
    if err:
        raise HTTPException(status_code=503, detail=err["detail"])

    account_number = f"ACC{random.randint(1000000000, 9999999999)}"
    account = Account(
        customer_id=req.customer_id,
        account_number=account_number,
        account_type=req.account_type,
        balance=req.initial_balance,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    log.info("account created", account_id=account.id, customer_id=req.customer_id)
    return _to_response(account)


@app.get("/accounts/{account_id}", response_model=AccountResponse)
async def get_account(account_id: str, db: Session = Depends(get_db)):
    err = await apply_chaos(SERVICE)
    if err:
        raise HTTPException(status_code=503, detail=err["detail"])

    account = _get_or_404(db, account_id)
    return _to_response(account)


@app.get("/accounts/customer/{customer_id}", response_model=list[AccountResponse])
async def list_accounts_by_customer(customer_id: str, db: Session = Depends(get_db)):
    accounts = db.query(Account).filter(Account.customer_id == customer_id).all()
    return [_to_response(a) for a in accounts]


@app.patch("/accounts/{account_id}/balance", response_model=AccountResponse)
async def update_balance(account_id: str, req: BalanceUpdate, db: Session = Depends(get_db)):
    """Internal endpoint — called by transaction-service only."""
    err = await apply_chaos(SERVICE)
    if err:
        raise HTTPException(status_code=503, detail=err["detail"])

    account = _get_or_404(db, account_id)

    if account.status != "active":
        raise HTTPException(status_code=422, detail=f"Account is {account.status}")

    new_balance = account.balance + req.amount
    if new_balance < 0 and account.account_type != "credit":
        raise HTTPException(status_code=422, detail="Insufficient funds")

    account.balance = round(new_balance, 2)
    db.commit()
    db.refresh(account)
    log.info("balance updated", account_id=account_id, delta=req.amount, new_balance=account.balance, op=req.operation)
    return _to_response(account)


@app.patch("/accounts/{account_id}/status")
async def update_status(account_id: str, status: str, db: Session = Depends(get_db)):
    account = _get_or_404(db, account_id)
    account.status = status
    db.commit()
    log.info("account status changed", account_id=account_id, status=status)
    return {"account_id": account_id, "status": status}


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
    log.info("chaos config cleared", service=SERVICE)
    return {"service": SERVICE, "chaos": "cleared"}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_or_404(db: Session, account_id: str) -> Account:
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


def _to_response(a: Account) -> dict:
    return {
        "id": a.id,
        "customer_id": a.customer_id,
        "account_number": a.account_number,
        "account_type": a.account_type,
        "balance": a.balance,
        "status": a.status,
        "created_at": a.created_at.isoformat(),
    }
