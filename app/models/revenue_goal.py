"""Revenue goal tracking model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RevenueGoal(Base):
    __tablename__ = "revenue_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="org")  # org, team, user
    scope_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    period: Mapped[str] = mapped_column(String(20), nullable=False)  # 2026-Q1, 2026-03
    period_type: Mapped[str] = mapped_column(String(20), nullable=False, default="quarterly")
    target_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    current_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    stretch_amount: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attainment_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    gap: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
