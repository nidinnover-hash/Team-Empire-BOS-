"""Win/loss analysis model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WinLossRecord(Base):
    __tablename__ = "win_loss_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    deal_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False)  # won, lost
    primary_reason: Mapped[str] = mapped_column(String(100), nullable=False)
    secondary_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    competitor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    deal_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    sales_cycle_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by_user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
