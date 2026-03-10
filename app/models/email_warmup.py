"""Email warmup tracking model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EmailWarmup(Base):
    __tablename__ = "email_warmups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    email_address: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    current_daily: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    target_daily: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    ramp_increment: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    warmup_day: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reputation_score: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
