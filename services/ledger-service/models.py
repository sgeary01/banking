import uuid
from datetime import datetime
from sqlalchemy import String, Float, DateTime
from sqlalchemy.orm import Mapped, mapped_column
import sys
sys.path.insert(0, "/app/shared")
from database import Base


class LedgerEntry(Base):
    __tablename__ = "ledger_entries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    transaction_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    account_id: Mapped[str] = mapped_column(String, index=True, nullable=False)
    entry_type: Mapped[str] = mapped_column(String, nullable=False)  # credit | debit
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
