import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column
import sys
sys.path.insert(0, "/app/shared")
from database import Base


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    account_number: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    account_type: Mapped[str] = mapped_column(String, nullable=False)  # checking | savings | credit
    balance: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String, default="active")  # active | frozen | closed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
