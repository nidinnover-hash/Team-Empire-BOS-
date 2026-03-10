"""Sales forecast rollup model."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ForecastRollup(Base):
    __tablename__ = "forecast_rollups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(20), nullable=False)  # e.g. "2026-Q1", "2026-03"
    period_type: Mapped[str] = mapped_column(String(20), nullable=False, default="monthly")
    group_by: Mapped[str] = mapped_column(String(50), nullable=False, default="team")  # team, region, rep
    group_value: Mapped[str] = mapped_column(String(100), nullable=False)
    committed: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    best_case: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    pipeline: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    weighted_pipeline: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    closed_won: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    target: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attainment_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
