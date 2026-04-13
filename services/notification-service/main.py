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
from models import Notification

log = get_logger()
SERVICE = "notification-service"


@asynccontextmanager
async def lifespan(app):
    init_db()
    log.info("notification-service started")
    yield

app = create_app("Notification Service", lifespan=lifespan)


# ── Schemas ────────────────────────────────────────────────────────────────────

class SendNotificationRequest(BaseModel):
    customer_id: Optional[str] = None
    notification_type: str = "transaction"
    channel: str = "email"
    message: str


class NotificationResponse(BaseModel):
    id: str
    customer_id: Optional[str]
    notification_type: str
    channel: str
    message: str
    status: str
    created_at: str


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.post("/notifications/send", response_model=NotificationResponse, status_code=201)
async def send_notification(req: SendNotificationRequest, db: Session = Depends(get_db)):
    err = await apply_chaos(SERVICE)
    if err:
        raise HTTPException(status_code=503, detail=err["detail"])

    # Simulate delivery (log it — in reality would call email/SMS provider)
    log.info("notification sent", customer_id=req.customer_id, channel=req.channel,
             type=req.notification_type, message=req.message[:80])

    notification = Notification(
        customer_id=req.customer_id,
        notification_type=req.notification_type,
        channel=req.channel,
        message=req.message,
        status="sent",
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return _to_response(notification)


@app.get("/notifications/customer/{customer_id}", response_model=list[NotificationResponse])
async def get_customer_notifications(customer_id: str, limit: int = 50, db: Session = Depends(get_db)):
    notifications = db.query(Notification).filter(
        Notification.customer_id == customer_id
    ).order_by(Notification.created_at.desc()).limit(limit).all()
    return [_to_response(n) for n in notifications]


@app.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(limit: int = 100, db: Session = Depends(get_db)):
    notifications = db.query(Notification).order_by(
        Notification.created_at.desc()
    ).limit(limit).all()
    return [_to_response(n) for n in notifications]


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


def _to_response(n: Notification) -> dict:
    return {
        "id": n.id,
        "customer_id": n.customer_id,
        "notification_type": n.notification_type,
        "channel": n.channel,
        "message": n.message,
        "status": n.status,
        "created_at": n.created_at.isoformat(),
    }
