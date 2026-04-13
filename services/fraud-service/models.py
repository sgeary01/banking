import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column
import sys
sys.path.insert(0, "/app/shared")
from database import Base


class FraudAlert(Base):
    __tablename__ = "fraud_alerts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    reasons: Mapped[str] = mapped_column(String, nullable=False)  # JSON-encoded list
    status: Mapped[str] = mapped_column(String, default="open")  # open | reviewed | dismissed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
