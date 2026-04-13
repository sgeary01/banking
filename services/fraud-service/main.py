import json
import sys
from datetime import datetime, timedelta
sys.path.insert(0, "/app/shared")

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from observability import create_app, get_logger
from database import get_db, init_db
from chaos import apply_chaos
from models import FraudAlert

log = get_logger()
SERVICE = "fraud-service"

# Tunable thresholds
HIGH_AMOUNT_THRESHOLD = 5000.0
VELOCITY_WINDOW_MINUTES = 10
VELOCITY_MAX_TRANSACTIONS = 5
LATE_NIGHT_HOURS = (0, 5)  # midnight to 5am


@asynccontextmanager
async def lifespan(app):
    init_db()
    log.info("fraud-service started")
    yield

app = create_app("Fraud Service", lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class AnalyzeRequest(BaseModel):
    id: str
    transaction_type: str
    source_account_id: Optional[str] = None
    destination_account_id: Optional[str] = None
    amount: float
    currency: str = "USD"
    status: str
    description: Optional[str] = None
    created_at: str


class FraudAlertResponse(BaseModel):
    id: str
    transaction_id: str
    account_id: str
    risk_score: float
    reasons: list[str]
    status: str
    created_at: str


# ── Fraud rules ────────────────────────────────────────────────────────────────

def _analyze(tx: AnalyzeRequest, db: Session) -> tuple[float, list[str]]:
    score = 0.0
    reasons = []

    # Rule 1: High-value transaction
    if tx.amount > HIGH_AMOUNT_THRESHOLD:
        score += 0.4
        reasons.append(f"High value transaction: ${tx.amount:.2f}")

    # Rule 2: Late-night transaction
    created = datetime.fromisoformat(tx.created_at)
    if LATE_NIGHT_HOURS[0] <= created.hour < LATE_NIGHT_HOURS[1]:
        score += 0.3
        reasons.append(f"Late night transaction at {created.strftime('%H:%M')}")

    # Rule 3: Velocity check — many transactions in short window
    account_id = tx.source_account_id or tx.destination_account_id
    if account_id:
        window_start = datetime.utcnow() - timedelta(minutes=VELOCITY_WINDOW_MINUTES)
        recent_alerts = db.query(FraudAlert).filter(
            FraudAlert.account_id == account_id,
            FraudAlert.created_at >= window_start,
        ).count()
        if recent_alerts >= VELOCITY_MAX_TRANSACTIONS:
            score += 0.5
            reasons.append(f"High transaction velocity: {recent_alerts} transactions in {VELOCITY_WINDOW_MINUTES}m")

    # Rule 4: Round number amounts (common in fraud)
    if tx.amount % 1000 == 0 and tx.amount >= 1000:
        score += 0.1
        reasons.append(f"Suspicious round amount: ${tx.amount:.0f}")

    return min(score, 1.0), reasons


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/fraud/analyze", status_code=201)
async def analyze_transaction(req: AnalyzeRequest, db: Session = Depends(get_db)):
    err = await apply_chaos(SERVICE)
    if err:
        raise HTTPException(status_code=503, detail=err["detail"])

    account_id = req.source_account_id or req.destination_account_id or "unknown"
    risk_score, reasons = _analyze(req, db)

    if risk_score > 0:
        alert = FraudAlert(
            transaction_id=req.id,
            account_id=account_id,
            risk_score=risk_score,
            reasons=json.dumps(reasons),
        )
        db.add(alert)
        db.commit()
        db.refresh(alert)
        log.warning("fraud alert created", transaction_id=req.id, risk_score=risk_score, reasons=reasons)
        return _to_response(alert)

    log.info("transaction cleared", transaction_id=req.id, risk_score=risk_score)
    return {"transaction_id": req.id, "risk_score": 0.0, "status": "clear"}


@app.get("/fraud/alerts", response_model=list[FraudAlertResponse])
async def list_alerts(status: Optional[str] = None, limit: int = 50, db: Session = Depends(get_db)):
    q = db.query(FraudAlert)
    if status:
        q = q.filter(FraudAlert.status == status)
    alerts = q.order_by(FraudAlert.created_at.desc()).limit(limit).all()
    return [_to_response(a) for a in alerts]


@app.get("/fraud/alerts/{alert_id}", response_model=FraudAlertResponse)
async def get_alert(alert_id: str, db: Session = Depends(get_db)):
    alert = db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return _to_response(alert)


@app.patch("/fraud/alerts/{alert_id}/status")
async def update_alert_status(alert_id: str, status: str, db: Session = Depends(get_db)):
    alert = db.query(FraudAlert).filter(FraudAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.status = status
    db.commit()
    log.info("fraud alert status updated", alert_id=alert_id, status=status)
    return {"alert_id": alert_id, "status": status}


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


def _to_response(a: FraudAlert) -> dict:
    return {
        "id": a.id,
        "transaction_id": a.transaction_id,
        "account_id": a.account_id,
        "risk_score": a.risk_score,
        "reasons": json.loads(a.reasons),
        "status": a.status,
        "created_at": a.created_at.isoformat(),
    }
