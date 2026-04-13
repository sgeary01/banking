import uuid
from datetime import datetime
from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column
import sys
sys.path.insert(0, "/app/shared")
from database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str | None] = mapped_column(String, index=True, nullable=True)
    notification_type: Mapped[str] = mapped_column(String, nullable=False)  # transaction | alert | system
    channel: Mapped[str] = mapped_column(String, nullable=False)  # email | sms | push
    message: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="sent")  # sent | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
