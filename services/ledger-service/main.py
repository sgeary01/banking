import sys
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from observability import create_app, get_logger
from database import get_db, init_db
from models import LedgerEntry

log = get_logger()


@asynccontextmanager
async def lifespan(app):
    init_db()
    log.info("ledger-service started")
    yield

app = create_app("Ledger Service", lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class LedgerEntryCreate(BaseModel):
    transaction_id: str
    account_id: str
    entry_type: str  # credit | debit
    amount: float
    description: Optional[str] = None


class LedgerEntryResponse(BaseModel):
    id: str
    transaction_id: str
    account_id: str
    entry_type: str
    amount: float
    description: Optional[str]
    created_at: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/ledger/entries", response_model=LedgerEntryResponse, status_code=201)
async def create_entry(req: LedgerEntryCreate, db: Session = Depends(get_db)):
    entry = LedgerEntry(**req.model_dump())
    db.add(entry)
    db.commit()
    db.refresh(entry)
    log.info("ledger entry created", entry_id=entry.id, account_id=entry.account_id,
             entry_type=entry.entry_type, amount=entry.amount)
    return _to_response(entry)


@app.get("/ledger/account/{account_id}", response_model=list[LedgerEntryResponse])
async def get_account_ledger(account_id: str, limit: int = 100, db: Session = Depends(get_db)):
    entries = db.query(LedgerEntry).filter(
        LedgerEntry.account_id == account_id
    ).order_by(LedgerEntry.created_at.desc()).limit(limit).all()
    return [_to_response(e) for e in entries]


@app.get("/ledger/transaction/{transaction_id}", response_model=list[LedgerEntryResponse])
async def get_transaction_entries(transaction_id: str, db: Session = Depends(get_db)):
    entries = db.query(LedgerEntry).filter(
        LedgerEntry.transaction_id == transaction_id
    ).all()
    return [_to_response(e) for e in entries]


def _to_response(e: LedgerEntry) -> dict:
    return {
        "id": e.id,
        "transaction_id": e.transaction_id,
        "account_id": e.account_id,
        "entry_type": e.entry_type,
        "amount": e.amount,
        "description": e.description,
        "created_at": e.created_at.isoformat(),
    }
